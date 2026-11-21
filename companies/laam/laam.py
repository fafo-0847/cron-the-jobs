from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from companies._shared import peopleforce


sourceUrl = "https://laam.peopleforce.io/careers"
requestTimeoutSeconds = 60
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
laamJsonPath = Path(__file__).with_name("laam.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, link: str) -> str:
	raw = title + link
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def parseMetaLine(metaText: str) -> tuple[str, str, str]:
	rawParts = metaText.split(",")
	cleanedParts: list[str] = []
	partIndex = 0
	while partIndex < len(rawParts):
		cleanedPart = rawParts[partIndex].strip()
		cleanedParts.append(cleanedPart)
		partIndex = partIndex + 1

	department = cleanedParts[0] if len(cleanedParts) > 0 else ""
	jobType = cleanedParts[1] if len(cleanedParts) > 1 else ""
	locationParts = cleanedParts[2:] if len(cleanedParts) > 2 else []
	location = ", ".join(locationParts)

	return department, jobType, location


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching Laam jobs from %s", url)
	allJobs: list[dict[str, str]] = []
	confirmedEmpty = False
	try:
		result = await peopleforce.fetchCareersJobs(url, generateJobId)
		allJobs = result["jobs"]
		confirmedEmpty = result["confirmedEmpty"]
		logger.info("Parsed %d total Laam jobs", len(allJobs))
	except Exception as error:
		logger.exception("Failed to fetch Laam jobs: %s", error)
		allJobs = []

	fetchedAt = datetime.now(timezone.utc).isoformat()
	state = {
		"sourceUrl": url,
		"fetchedAt": fetchedAt,
		"state": "open",
		"jobs": allJobs,
		"confirmedEmpty": confirmedEmpty,
	}
	return state


def defaultSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	snapshot = {
		"sourceUrl": url,
		"fetchedAt": "",
		"state": "open",
		"jobs": [],
	}
	return snapshot


def loadExistingSnapshot() -> dict[str, Any]:
	if not laamJsonPath.exists():
		return defaultSnapshot()

	content = laamJsonPath.read_text(encoding="utf-8")
	if not content.strip():
		return defaultSnapshot()

	data = json.loads(content)
	return data


def buildSnapshot(state: dict[str, Any], existingSnapshot: dict[str, Any]) -> dict[str, Any]:
	snapshot = dict(existingSnapshot)
	snapshot["sourceUrl"] = state.get("sourceUrl", sourceUrl)
	snapshot["fetchedAt"] = state.get("fetchedAt", "")
	snapshot["state"] = state.get("state", "open")
	snapshot["jobs"] = state.get("jobs", [])
	return snapshot


def writeSnapshot(snapshot: dict[str, Any]) -> None:
	output = json.dumps(snapshot, indent=2, ensure_ascii=False)
	laamJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated Laam snapshot at %s", laamJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update Laam snapshot: %s", error)
		snapshot = buildSnapshot(defaultSnapshot(url), existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		return snapshot


async def runMain() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--url", default=sourceUrl)
	args = parser.parse_args()

	snapshot = await updateSnapshot(args.url)
	output = json.dumps(snapshot, indent=2, ensure_ascii=False)
	print(output)


if __name__ == "__main__":
	asyncio.run(runMain())
