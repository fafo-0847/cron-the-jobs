import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

companyName = "mashreqbank"
companyDir = Path(__file__).parent
snapshotPath = companyDir / f"{companyName}.json"

apiHost = "https://hcld.fa.em2.oraclecloud.com"
apiPath = "/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
apiQueryBase = (
	"onlyData=true"
	"&expand=requisitionList.workLocation,requisitionList.otherWorkLocations,"
	"requisitionList.secondaryLocations,flexFieldsFacet.values,requisitionList.requisitionFlexFields"
	"&finder=findReqs;siteNumber=CX_1,"
	"facetsList=LOCATIONS%3BWORK_LOCATIONS%3BWORKPLACE_TYPES%3BTITLES%3BCATEGORIES%3BORGANIZATIONS%3BPOSTING_DATES%3BFLEX_FIELDS,"
	"limit={limit},locationId=300000000300311,sortBy=POSTING_DATES_DESC,offset={offset}"
)
jobDetailBase = f"{apiHost}/hcmUI/CandidateExperience/en/sites/CX_1/job"

sourceUrl = f"{apiHost}{apiPath}?{apiQueryBase.format(limit=25, offset=0)}"

pageLimit = 25


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def loadExistingSnapshot() -> dict[str, Any]:
	fileExists = snapshotPath.exists()
	if fileExists:
		try:
			rawText = snapshotPath.read_text()
			snapshot = json.loads(rawText)
			return snapshot
		except Exception as error:
			logger.warning("Failed to load existing snapshot for %s: %s", companyName, error)
			return {"jobs": []}
	else:
		return {"jobs": []}


async def fetchPage(session: aiohttp.ClientSession, offset: int) -> dict[str, Any]:
	query = apiQueryBase.format(limit=pageLimit, offset=offset)
	pageUrl = f"{apiHost}{apiPath}?{query}"
	try:
		response = await session.get(pageUrl, timeout=aiohttp.ClientTimeout(total=30))
		response.raise_for_status()
		payload = await response.json()
		return payload
	except Exception as error:
		logger.warning("Failed to fetch %s page at offset %d: %s", companyName, offset, error)
		return {}


def parseJobsFromRequisitions(requisitions: list) -> list:
	newJobs = []
	index = 0
	while index < len(requisitions):
		requisition = requisitions[index]
		title = requisition.get("Title", "")
		stableId = str(requisition.get("Id", ""))
		jobId = generateJobId(title, stableId)
		link = f"{jobDetailBase}/{stableId}"
		location = requisition.get("PrimaryLocation", "")
		department = requisition.get("Organization", "") or ""
		jobType = requisition.get("WorkplaceType", "") or ""
		postedAt = requisition.get("PostedDate", "")
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
		newJobs.append(job)
		index = index + 1
	return newJobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	allRequisitions = []
	currentOffset = 0
	totalJobsCount = None
	async with aiohttp.ClientSession() as session:
		keepFetching = True
		while keepFetching:
			payload = await fetchPage(session, currentOffset)
			payloadIsEmpty = payload == {}
			if payloadIsEmpty:
				keepFetching = False
				continue
			items = payload.get("items", [])
			itemsIsEmpty = len(items) == 0
			if itemsIsEmpty:
				keepFetching = False
				continue
			firstItem = items[0]
			totalJobsCount = firstItem.get("TotalJobsCount", 0)
			requisitionList = firstItem.get("requisitionList", [])
			allRequisitions.extend(requisitionList)
			currentOffset = currentOffset + pageLimit
			reachedEnd = totalJobsCount is not None and currentOffset >= totalJobsCount
			if reachedEnd:
				keepFetching = False
	jobs = parseJobsFromRequisitions(allRequisitions)
	state = {"jobs": jobs}
	return state


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobs = state.get("jobs", [])
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("Suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
		return dict(existingSnapshot)
	snapshot = {
		"sourceUrl": sourceUrl,
		"fetchedAt": datetime.now(timezone.utc).isoformat(),
		"state": "open",
		"jobs": newJobs,
	}
	return snapshot


def writeSnapshot(snapshot: dict) -> None:
	try:
		snapshotText = json.dumps(snapshot, indent=2)
		snapshotPath.write_text(snapshotText)
	except Exception as error:
		logger.warning("Failed to write snapshot for %s: %s", companyName, error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	logging.basicConfig(level=logging.INFO)
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("Fetched %d jobs for %s", jobCount, companyName)


if __name__ == "__main__":
	asyncio.run(runMain())