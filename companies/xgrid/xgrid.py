import datetime
import hashlib
import json
import logging
import urllib.request
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("xgrid")

disabledReason = "2026-11: xgrid's Freshteam account was deleted; xgrid.co/open-positions lists no jobs. Re-enable when they pick a new careers source."
sourceUrl = "https://xgrid.freshteam.com/hire/widgets/jobs.json"
snapshotPath = Path(__file__).parent / "xgrid.json"

jobTypeLabels = {
	1: "Full time",
	2: "Part time",
	3: "Internship",
	4: "Contract",
	5: "Temporary",
}


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def loadExistingSnapshot() -> dict[str, Any]:
	snapshotExists = snapshotPath.exists()
	if snapshotExists:
		fileContent = snapshotPath.read_text(encoding="utf-8")
		existingSnapshot = json.loads(fileContent)
	else:
		existingSnapshot = dict(sourceUrl=sourceUrl, fetchedAt="", state="unknown", jobs=[])
	return existingSnapshot


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	errorOccurred = False
	try:
		requestHeaders = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.xgrid.co", "Referer": "https://www.xgrid.co/"}
		request = urllib.request.Request(url, headers=requestHeaders)
		response = urllib.request.urlopen(request, timeout=30)
		responseBody = response.read()
		isInvalidDomainPage = b"invalid-domain" in responseBody[:3000]
		if isInvalidDomainPage:
			# Seen since Nov 2026: the Freshteam account behind xgrid.co/open-positions no longer
			# exists, so xgrid's own site lists no jobs either. Needs a new source when they pick one.
			raise ValueError("xgrid Freshteam account not found (Freshteam 'invalid domain' page); xgrid.co/open-positions shows no jobs")
		payload = json.loads(responseBody)
		rawJobs = payload.get("jobs", [])
		jobIndex = 0
		jobCount = len(rawJobs)
		while jobIndex < jobCount:
			rawJob = rawJobs[jobIndex]
			job = parseJob(rawJob)
			jobFound = job is not None
			if jobFound:
				jobs.append(job)
			jobIndex = jobIndex + 1
	except Exception as fetchException:
		errorOccurred = True
		logger.exception("Failed to fetch xgrid jobs: %s", fetchException)
	stateResult = "error" if errorOccurred else "open"
	state = dict(jobs=jobs, state=stateResult)
	return state


def parseJob(rawJob: dict) -> dict[str, Any]:
	parsedJob = None
	try:
		isDeleted = rawJob.get("deleted", False)
		if isDeleted:
			return parsedJob
		title = rawJob.get("title", "")
		titleIsEmpty = title is None or title == ""
		if titleIsEmpty:
			return parsedJob
		stableId = rawJob.get("unique_id", "")
		stableIdIsEmpty = stableId is None or stableId == ""
		if stableIdIsEmpty:
			numericId = rawJob.get("id", "")
			stableId = str(numericId)
		link = rawJob.get("url", "")
		jobTypeCode = rawJob.get("job_type")
		jobType = jobTypeLabels.get(jobTypeCode, "")
		jobId = generateJobId(title, stableId)
		parsedJob = dict(
			id=jobId,
			title=title,
			link=link,
			location="",
			department="",
			jobType=jobType,
			postedAt=rawJob.get("created_at", ""),
			state="open",
		)
	except Exception as parseException:
		logger.exception("Failed to parse xgrid job: %s", parseException)
	return parsedJob


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	newJobs = state.get("jobs", [])
	oldJobs = existingSnapshot.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("Suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
		return dict(existingSnapshot)
	fetchedAt = datetime.datetime.now(datetime.timezone.utc).isoformat()
	snapshot = dict(
		sourceUrl=sourceUrl,
		fetchedAt=fetchedAt,
		state=state.get("state", "unknown"),
		jobs=newJobs,
	)
	return snapshot


def writeSnapshot(snapshot: dict) -> None:
	snapshotJson = json.dumps(snapshot, indent=2)
	snapshotPath.write_text(snapshotJson, encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("xgrid: wrote %d jobs", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())