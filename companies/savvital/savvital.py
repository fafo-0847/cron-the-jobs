import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("savvital")

sourceUrl = "https://savvital.breezy.hr"
baseUrl = "https://savvital.breezy.hr"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "savvital.json"


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
	hasEnoughSegments = len(segments) >= 2
	isPositionPath = hasEnoughSegments and segments[0] == "p"
	if isPositionPath:
		lastSegment = segments[-1]
		stableId = lastSegment.split("-")[0]
	else:
		stableId = ""
	return stableId


def normalizeText(rawText) -> str:
	isNone = rawText is None
	if isNone:
		return ""
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


# Breezy HR publishes the board as JSON at <board>/json (what the board page renders from).
# The li.position / h2.group-header markup stopped matching on GitHub runners in Nov 2026,
# so read the JSON instead. stableId stays the Breezy position id, so ids do not change.
breezyJsonUrl = baseUrl + "/json"
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def parsePosition(position: dict) -> dict[str, Any] | None:
	title = normalizeText(position.get("name") or "")
	link = normalizeText(position.get("url") or "")
	if title == "" or link == "":
		return None
	positionId = normalizeText(str(position.get("id") or "")) or extractStableId(link.replace(baseUrl, ""))
	location = position.get("location") or {}
	country = normalizeText((location.get("country") or {}).get("name") or "")
	remoteDetails = location.get("remote_details") or {}
	isRemote = bool(location.get("is_remote"))
	remoteType = normalizeText(remoteDetails.get("label") or ("Remote" if isRemote else ""))
	job = {
		"id": generateJobId(title, positionId),
		"title": title,
		"link": link,
		"location": country or normalizeText(location.get("name") or ""),
		"department": normalizeText(position.get("department") or "") or country,
		"jobType": normalizeText((position.get("type") or {}).get("name") or ""),
		"remoteType": remoteType,
		"postedAt": position.get("published_date") or "",
		"state": "open",
	}
	return job


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	confirmedEmpty = False
	try:
		timeout = aiohttp.ClientTimeout(total=30)
		async with aiohttp.ClientSession(headers={"User-Agent": userAgent}, timeout=timeout) as session:
			async with session.get(breezyJsonUrl) as response:
				response.raise_for_status()
				positions = await response.json(content_type=None)
		if not isinstance(positions, list):
			raise ValueError(f"unexpected Breezy payload: {str(positions)[:200]}")
		jobs = [job for job in (parsePosition(position) for position in positions) if job is not None]
		confirmedEmpty = len(positions) == 0
	except Exception as error:
		logger.exception("savvital: fetchState failed: %s", error)
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
		logger.exception("savvital: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("savvital: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("savvital: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("savvital: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())