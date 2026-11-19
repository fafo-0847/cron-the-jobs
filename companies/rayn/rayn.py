import datetime
import hashlib
import json
import logging
import urllib.request
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rayn")

sourceUrl = "https://rayngroup.bamboohr.com/careers/list"
careerBaseUrl = "https://rayngroup.bamboohr.com/careers/"
snapshotPath = Path(__file__).parent / "rayn.json"


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
		request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
		response = urllib.request.urlopen(request, timeout=30)
		responseBody = response.read()
		payload = json.loads(responseBody)
		rawJobs = payload.get("result", [])
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
		logger.exception("Failed to fetch rayn jobs: %s", fetchException)
	stateResult = "error" if errorOccurred else "open"
	state = dict(jobs=jobs, state=stateResult)
	return state


def parseJob(rawJob: dict) -> dict[str, Any]:
	parsedJob = None
	try:
		title = rawJob.get("jobOpeningName", "")
		titleIsEmpty = title is None or title == ""
		if titleIsEmpty:
			return parsedJob
		stableId = str(rawJob.get("id", ""))
		stableIdIsEmpty = stableId == ""
		if stableIdIsEmpty:
			return parsedJob
		link = careerBaseUrl + stableId
		department = rawJob.get("departmentLabel", "")
		jobType = rawJob.get("employmentStatusLabel", "")
		location = buildLocation(rawJob)
		jobId = generateJobId(title, stableId)
		parsedJob = dict(
			id=jobId,
			title=title,
			link=link,
			location=location,
			department=department,
			jobType=jobType,
			postedAt="",
			state="open",
		)
	except Exception as parseException:
		logger.exception("Failed to parse rayn job: %s", parseException)
	return parsedJob


def buildLocation(rawJob: dict) -> str:
	atsLocation = rawJob.get("atsLocation", {})
	atsLocationIsValid = atsLocation is not None
	if not atsLocationIsValid:
		atsLocation = {}
	city = atsLocation.get("city")
	province = atsLocation.get("province")
	country = atsLocation.get("country")
	locationParts = []
	cityIsValid = city is not None and city != ""
	if cityIsValid:
		locationParts.append(city)
	provinceIsValid = province is not None and province != ""
	if provinceIsValid:
		locationParts.append(province)
	countryIsValid = country is not None and country != ""
	if countryIsValid:
		locationParts.append(country)
	location = ", ".join(locationParts)
	return location


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
	logger.info("rayn: wrote %d jobs", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())