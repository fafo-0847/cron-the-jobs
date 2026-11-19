import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nakisa")

sourceUrl = "https://boards-api.greenhouse.io/v1/boards/nakisa/jobs?content=true"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "nakisa.json"


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


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
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
				stableId = str(rawJob.get("id", ""))
				linkRaw = rawJob.get("absolute_url", "")
				link = normalizeText(linkRaw)
				locationData = rawJob.get("location", {})
				hasLocationData = locationData is not None
				if hasLocationData:
					locationName = locationData.get("name", "")
				else:
					locationName = ""
				location = normalizeText(locationName)
				departmentsData = rawJob.get("departments", [])
				hasDepartments = len(departmentsData) > 0
				if hasDepartments:
					departmentName = departmentsData[0].get("name", "")
				else:
					departmentName = ""
				department = normalizeText(departmentName)
				postedAtRaw = rawJob.get("first_published", "")
				hasPostedAtRaw = postedAtRaw is not None
				if hasPostedAtRaw:
					postedAt = postedAtRaw
				else:
					postedAt = ""
				requisitionId = rawJob.get("requisition_id", "")
				jobId = generateJobId(title, stableId)
				job = {
					"id": jobId,
					"title": title,
					"link": link,
					"location": location,
					"department": department,
					"jobType": "",
					"requisitionId": requisitionId,
					"postedAt": postedAt,
					"state": "open",
				}
				jobs.append(job)
			index = index + 1
	except Exception as error:
		logger.exception("nakisa: fetchState failed: %s", error)
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
		logger.exception("nakisa: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("nakisa: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("nakisa: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("nakisa: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())