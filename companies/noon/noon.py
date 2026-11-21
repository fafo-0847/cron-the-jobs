import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("noon")

apiUrl = "https://api.ashbyhq.com/posting-api/job-board/noon-design"
sourceUrl = "https://jobs.ashbyhq.com/noon-design"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "noon.json"


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


async def fetchState(url: str = apiUrl) -> dict[str, Any]:
	jobs = []
	confirmedEmpty = False
	try:
		async with aiohttp.ClientSession() as session:
			async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
				response.raise_for_status()
				payload = await response.json()
		rawJobs = payload.get("jobs")
		isValidPayload = isinstance(rawJobs, list)
		if not isValidPayload:
			raise ValueError(f"unexpected Ashby payload keys: {list(payload)[:5]}")
		confirmedEmpty = len(rawJobs) == 0
		index = 0
		while index < len(rawJobs):
			rawJob = rawJobs[index]
			titleRaw = rawJob.get("title", "")
			title = normalizeText(titleRaw)
			hasTitle = title != ""
			if hasTitle:
				stableId = normalizeText(str(rawJob.get("id", "")))
				department = rawJob.get("department", "")
				hasDepartment = department != "" and department is not None
				if not hasDepartment:
					department = rawJob.get("team", "")
				department = normalizeText(department)
				location = normalizeText(rawJob.get("location", ""))
				jobType = normalizeText(rawJob.get("employmentType", ""))
				linkRaw = rawJob.get("jobUrl", "")
				link = normalizeText(linkRaw)
				hasLink = link != ""
				if not hasLink:
					link = normalizeText(rawJob.get("applyUrl", ""))
				compensation = normalizeText(rawJob.get("compensationTierSummary", ""))
				postedAtRaw = rawJob.get("publishedAt", "")
				hasPostedAtRaw = postedAtRaw is not None
				if hasPostedAtRaw:
					postedAt = postedAtRaw
				else:
					postedAt = ""
				jobId = generateJobId(title, stableId)
				job = {
					"id": jobId,
					"title": title,
					"link": link,
					"location": location,
					"department": department,
					"jobType": jobType,
					"compensation": compensation,
					"postedAt": postedAt,
					"state": "open",
				}
				jobs.append(job)
			index = index + 1
	except Exception as error:
		logger.exception("noon: fetchState failed: %s", error)
		confirmedEmpty = False
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
		logger.exception("noon: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("noon: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("noon: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = apiUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("noon: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())