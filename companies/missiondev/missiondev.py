import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("missiondev")

apiUrlTemplate = "https://mission.dev/api/opportunities?page={page}&perPage=12"
sourceUrl = "https://mission.dev/api/opportunities?page=1&perPage=12"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "missiondev.json"
perPage = 12
maxPages = 50


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


def joinTaggableNames(taggableList) -> str:
	isNone = taggableList is None
	if isNone:
		return ""
	names = []
	index = 0
	while index < len(taggableList):
		item = taggableList[index]
		name = item.get("name", "")
		hasName = name != "" and name is not None
		if hasName:
			names.append(name)
		index = index + 1
	joined = ", ".join(names)
	return joined


async def fetchPage(session, pageNumber: int) -> list:
	url = apiUrlTemplate.format(page=pageNumber)
	async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
		payload = await response.json()
	roles = payload.get("roles", [])
	return roles


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with aiohttp.ClientSession() as session:
			pageNumber = 1
			keepGoing = True
			while keepGoing and pageNumber <= maxPages:
				rawRoles = await fetchPage(session, pageNumber)
				roleCount = len(rawRoles)
				index = 0
				while index < roleCount:
					rawRole = rawRoles[index]
					nameRaw = rawRole.get("name", "")
					title = normalizeText(nameRaw)
					hasTitle = title != ""
					if hasTitle:
						stableId = normalizeText(rawRole.get("uuid", ""))
						slug = normalizeText(rawRole.get("slug", ""))
						locationsData = rawRole.get("locations", [])
						location = joinTaggableNames(locationsData)
						disciplinesData = rawRole.get("disciplines", [])
						department = joinTaggableNames(disciplinesData)
						primarySkills = joinTaggableNames(rawRole.get("primarySkills", []))
						secondarySkills = joinTaggableNames(rawRole.get("secondarySkills", []))
						jobType = normalizeText(rawRole.get("workArrangement", ""))
						engagementType = normalizeText(rawRole.get("engagementType", ""))
						postedAtRaw = rawRole.get("publishedAt", "")
						hasPostedAtRaw = postedAtRaw is not None
						if hasPostedAtRaw:
							postedAt = postedAtRaw
						else:
							postedAt = ""
						missionData = rawRole.get("mission", {})
						hasMissionData = missionData is not None
						if hasMissionData:
							missionName = normalizeText(missionData.get("name", ""))
							missionDescription = normalizeText(missionData.get("description", ""))
						else:
							missionName = ""
							missionDescription = ""
						jobId = generateJobId(title, stableId)
						job = {
							"id": jobId,
							"title": title,
							"link": "",
							"location": location,
							"department": department,
							"jobType": jobType,
							"engagementType": engagementType,
							"primarySkills": primarySkills,
							"secondarySkills": secondarySkills,
							"slug": slug,
							"missionName": missionName,
							"missionDescription": missionDescription,
							"postedAt": postedAt,
							"state": "open",
						}
						jobs.append(job)
					index = index + 1
				isShortPage = roleCount < perPage
				if isShortPage:
					keepGoing = False
				else:
					pageNumber = pageNumber + 1
	except Exception as error:
		logger.exception("missiondev: fetchState failed: %s", error)
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
		logger.exception("missiondev: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("missiondev: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("missiondev: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("missiondev: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())