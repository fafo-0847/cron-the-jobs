import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from companies._shared import bamboohr

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("algo")

sourceUrl = "https://www.algo.com/careers/#open-positions"
bambooCompany = "algomus"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "algo.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def extractStableId(elementId: str) -> str:
	prefix = "bhrPositionID_"
	hasPrefix = elementId.startswith(prefix)
	if hasPrefix:
		stableId = elementId[len(prefix):]
	else:
		stableId = ""
	return stableId


def normalizeText(rawText: str) -> str:
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


def normalizeLink(href: str) -> str:
	isProtocolRelative = href.startswith("//")
	if isProtocolRelative:
		link = "https:" + href
	else:
		link = href
	return link


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	# algo.com embeds the BambooHR widget for "algomus"; read its public JSON instead of the
	# rendered widget (.BambooHR-ATS-* markup), which algo.com stopped rendering reliably.
	jobs = []
	confirmedEmpty = False
	try:
		result = await bamboohr.fetchOpenings(bambooCompany, generateJobId)
		jobs = result["jobs"]
		confirmedEmpty = result["confirmedEmpty"]
	except Exception as error:
		logger.exception("algo: fetchState failed: %s", error)
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
		logger.exception("algo: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("algo: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("algo: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("algo: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())