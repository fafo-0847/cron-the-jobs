"""Snapshot plumbing for config-driven company scrapers.

A company module only declares its source and delegates here, e.g.

	source = {"type": "greenhouse", "slug": "acme"}
	async def fetchState(url=sourceUrl): return await company.fetchState(source, logger)
	def loadExistingSnapshot(): return company.loadSnapshot(snapshotPath, sourceUrl)
	def buildSnapshot(state, existing): return company.buildSnapshot(state, existing, sourceUrl, logger)
	def writeSnapshot(snapshot): company.writeSnapshot(snapshotPath, snapshot)

which gives main.py the same four functions every hand-written scraper exposes.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from companies._shared import ats


async def fetchState(source: dict, logger: logging.Logger) -> dict[str, Any]:
	jobs: list[dict] = []
	confirmedEmpty = False
	try:
		fetched = await ats.fetchSource(source)
		jobs = fetched["jobs"]
		confirmedEmpty = fetched["confirmedEmpty"]
		if len(jobs) == 0 and not confirmedEmpty and source.get("type") == "html" and source.get("expectJobs", True):
			logger.error("%s: no jobs matched on %s (layout changed or no openings)", logger.name, source.get("url"))
	except Exception as error:
		logger.exception("%s: fetchState failed: %s", logger.name, error)
	state = {"jobs": jobs, "state": "open", "confirmedEmpty": confirmedEmpty}
	return state


def emptySnapshot(sourceUrl: str) -> dict[str, Any]:
	return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def loadSnapshot(snapshotPath: Path, sourceUrl: str) -> dict[str, Any]:
	if not snapshotPath.exists():
		return emptySnapshot(sourceUrl)
	content = snapshotPath.read_text(encoding="utf-8")
	if not content.strip():
		return emptySnapshot(sourceUrl)
	return json.loads(content)


def buildSnapshot(state: dict, existingSnapshot: dict, sourceUrl: str, logger: logging.Logger) -> dict[str, Any]:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	if len(oldJobs) > 0 and len(newJobs) == 0:
		logger.warning("%s: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", logger.name, len(oldJobs), len(newJobs))
		return dict(existingSnapshot)
	return {
		"sourceUrl": sourceUrl,
		"fetchedAt": datetime.now(timezone.utc).isoformat(),
		"state": state.get("state", "open"),
		"jobs": newJobs,
	}


def writeSnapshot(snapshotPath: Path, snapshot: dict) -> None:
	snapshotPath.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
