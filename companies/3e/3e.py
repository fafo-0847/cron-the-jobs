import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("threee")

apiUrl = "https://api.ashbyhq.com/posting-api/job-board/3e?includeCompensation=true"
sourceUrl = "https://jobs.ashbyhq.com/3e"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "threee.json"


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
				stableId = normalizeText(str(rawJob.get("id", "")))
				department = normalizeText(rawJob.get("department", ""))
				team = normalizeText(rawJob.get("team", ""))
				location = normalizeText(rawJob.get("location", ""))
				jobType = normalizeText(rawJob.get("employmentType", ""))
				workplaceType = normalizeText(rawJob.get("workplaceType", ""))
				linkRaw = rawJob.get("jobUrl", "")
				link = normalizeText(linkRaw)
				hasLink = link != ""
				if not hasLink:
					link = normalizeText(rawJob.get("applyUrl", ""))
				compensationData = rawJob.get("compensation", {})
				hasCompensationData = compensationData is not None
				if hasCompensationData:
					compensationSummary = compensationData.get("compensationTierSummary", "")
				else:
					compensationSummary = ""
				compensation = normalizeText(compensationSummary)
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
					"team": team,
					"jobType": jobType,
					"workplaceType": workplaceType,
					"compensation": compensation,
					"postedAt": postedAt,
					"state": "open",
				}
				jobs.append(job)
			index = index + 1
	except Exception as error:
		logger.exception("threee: fetchState failed: %s", error)
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
		logger.exception("threee: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("threee: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("threee: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = apiUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("threee: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())