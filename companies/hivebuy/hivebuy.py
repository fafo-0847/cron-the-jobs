import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from companies._shared import joincom

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hivebuy")

sourceUrl = "https://www.hivebuy.com/en/career"
joinCompanySlug = "hivebuy"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "hivebuy.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def extractStableId(href: str) -> str:
	segments = href.strip("/").split("/")
	hasSegments = len(segments) > 0
	if hasSegments:
		lastSegment = segments[-1]
		leadingPart = lastSegment.split("-")[0]
	else:
		leadingPart = ""
	isNumeric = leadingPart.isdigit()
	if isNumeric:
		stableId = leadingPart
	else:
		stableId = ""
	return stableId


def normalizeText(rawText: str) -> str:
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	# hivebuy.com/en/career only links out to JOIN; the JOIN board is the source of truth
	# (and tells us reliably when there are 0 openings, which the HubSpot page cannot).
	jobs = []
	confirmedEmpty = False
	try:
		result = await joincom.fetchBoardJobs(joinCompanySlug, generateJobId)
		jobs = result["jobs"]
		confirmedEmpty = result["confirmedEmpty"]
	except Exception as error:
		logger.exception("hivebuy: fetchState failed: %s", error)
	state = {"jobs": jobs, "state": "open", "confirmedEmpty": confirmedEmpty}
	return state


def loadExistingSnapshot() -> dict[str, Any]:
	try:
		fileExists = snapshotPath.exists()
		if not fileExists:
			return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}
		rawText = snapshotPath.read_text(encoding="utf-8")
		snapshot = json.loads(rawText)
		return snapshot
	except Exception as error:
		logger.exception("hivebuy: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("hivebuy: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
		return dict(existingSnapshot)
	fetchedAt = datetime.datetime.now(datetime.timezone.utc).isoformat()
	snapshot = {
		"sourceUrl": sourceUrl,
		"fetchedAt": fetchedAt,
		"state": state.get("state", "open"),
		"jobs": newJobs,
	}
	return snapshot


def writeSnapshot(snapshot: dict) -> None:
	try:
		snapshotText = json.dumps(snapshot, indent=2, ensure_ascii=False)
		snapshotPath.write_text(snapshotText, encoding="utf-8")
	except Exception as error:
		logger.exception("hivebuy: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("hivebuy: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())