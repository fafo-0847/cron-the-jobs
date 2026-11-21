import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("harmonic")

# Harmonic moved from Greenhouse (boards/harmonic now 404s) to Ashby in Nov 2026.
apiUrl = "https://api.ashbyhq.com/posting-api/job-board/harmonic-ai"
sourceUrl = "https://jobs.ashbyhq.com/harmonic-ai"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "harmonic.json"


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


def parseAshbyJob(rawJob: dict) -> dict | None:
	title = normalizeText(rawJob.get("title", ""))
	hasTitle = title != ""
	if not hasTitle:
		return None
	stableId = normalizeText(str(rawJob.get("id", "")))
	department = normalizeText(rawJob.get("department") or rawJob.get("team") or "")
	location = normalizeText(rawJob.get("location") or "")
	jobType = normalizeText(rawJob.get("employmentType") or "")
	link = normalizeText(rawJob.get("jobUrl") or rawJob.get("applyUrl") or "")
	postedAt = rawJob.get("publishedAt") or ""
	jobId = generateJobId(title, stableId)
	job = {
		"id": jobId,
		"title": title,
		"link": link,
		"location": location,
		"department": department,
		"jobType": jobType,
		"postedAt": postedAt,
		"state": "open",
	}
	return job


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
		for rawJob in rawJobs:
			job = parseAshbyJob(rawJob)
			if job is not None:
				jobs.append(job)
	except Exception as error:
		logger.exception("harmonic: fetchState failed: %s", error)
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
		logger.exception("harmonic: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("harmonic: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("harmonic: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("harmonic: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())