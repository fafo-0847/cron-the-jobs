import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wamolabs")

sourceUrl = "http://www.wamolabs.com/api/jobs"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "wamolabs.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def normalizeText(rawText) -> str:
	isNone = rawText is None
	if isNone:
		return ""
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


def buildJob(title: str, stableId: str, link: str, location: str, department: str, jobType: str, extra: dict) -> dict:
	jobId = generateJobId(title, stableId)
	job = {
		"id": jobId,
		"title": title,
		"link": link,
		"location": location,
		"department": department,
		"jobType": jobType,
		"postedAt": "",
		"state": "open",
	}
	job.update(extra)
	return job


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with aiohttp.ClientSession() as session:
			async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
				payload = await response.json(content_type=None)
		isList = isinstance(payload, list)
		if isList:
			rawJobs = payload
		else:
			rawJobs = payload.get("jobs", [])
		index = 0
		while index < len(rawJobs):
			rawJob = rawJobs[index]
			isActive = rawJob.get("isActive", True)
			title = normalizeText(rawJob.get("title", ""))
			hasTitle = title != ""
			if hasTitle and isActive:
				stableId = normalizeText(str(rawJob.get("id", "")))
				location = normalizeText(rawJob.get("location", ""))
				commuteLocation = normalizeText(rawJob.get("canCommuteLocation", ""))
				isOnsite = rawJob.get("isOnsiteRequired", False)
				if isOnsite:
					jobType = "Onsite"
				else:
					jobType = ""
				workStartTime = normalizeText(rawJob.get("workStartTime", ""))
				isNightShift = rawJob.get("isNightShiftRequired", False)
				postedAt = rawJob.get("createdAt") or ""
				extra = {
					"commuteLocation": commuteLocation,
					"workStartTime": workStartTime,
					"isNightShift": isNightShift,
					"postedAt": postedAt,
				}
				job = buildJob(title, stableId, "", location, "", jobType, extra)
				jobs.append(job)
			index = index + 1
	except Exception as error:
		logger.exception("wamolabs: fetchState failed: %s", error)
	state = {"jobs": jobs, "state": "open"}
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
		logger.exception("wamolabs: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("wamolabs: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("wamolabs: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("wamolabs: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())