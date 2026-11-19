import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("overjet")

apiUrl = "https://api.ashbyhq.com/posting-api/job-board/Overjet"
sourceUrl = "https://www.overjet.com/careers"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "overjet.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def normalizeText(rawText: str) -> str:
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


async def fetchState(url: str = apiUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with aiohttp.ClientSession() as session:
			async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
				payload = await response.json()
		rawJobs = payload.get("jobs", [])
		index = 0
		while index < len(rawJobs):
			rawJob = rawJobs[index]
			titleRaw = rawJob.get("title", "")
			title = normalizeText(titleRaw)
			hasTitle = title != ""
			if hasTitle:
				stableId = rawJob.get("id", "")
				department = rawJob.get("department", "")
				hasDepartment = department != ""
				if not hasDepartment:
					department = rawJob.get("team", "")
				location = rawJob.get("location", "")
				jobType = rawJob.get("employmentType", "")
				link = rawJob.get("jobUrl", "")
				hasLink = link != ""
				if not hasLink:
					link = rawJob.get("applyUrl", "")
				postedAt = rawJob.get("publishedAt", "")
				jobId = generateJobId(title, stableId)
				job = {
					"id": jobId,
					"title": title,
					"link": link,
					"location": normalizeText(location),
					"department": normalizeText(department),
					"jobType": normalizeText(jobType),
					"postedAt": postedAt,
					"state": "open",
				}
				jobs.append(job)
			index = index + 1
	except Exception as error:
		logger.exception("overjet: fetchState failed: %s", error)
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
		logger.exception("overjet: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("overjet: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("overjet: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = apiUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("overjet: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())