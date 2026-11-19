import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

companyName = "mindstorm"
companyDir = Path(__file__).parent
snapshotPath = companyDir / f"{companyName}.json"

sourceUrl = "https://mindstormstudios.simplicant.com"

jobBlockPattern = re.compile(
	r'<a class="list-group-item" id="(\d+)_job_link".*?href="(.*?)".*?'
	r'<h3 class="list-group-item-title job-title">(.*?)</h3>.*?'
	r'<div class="list-group-item-subtitle job-subtitle">\s*(.*?)\s*</div>',
	re.DOTALL,
)


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


def normalizeText(text: str) -> str:
	normalized = text.replace("\xa0", " ").strip()
	return normalized


def normalizeLink(rawLink: str) -> str:
	isProtocolRelative = rawLink.startswith("//")
	if isProtocolRelative:
		link = "https:" + rawLink
	else:
		link = rawLink
	return link


def parseJobsFromHtml(htmlText: str) -> list:
	matches = jobBlockPattern.findall(htmlText)
	newJobs = []
	index = 0
	while index < len(matches):
		match = matches[index]
		stableId = match[0]
		rawLink = match[1]
		rawTitle = match[2]
		rawLocation = match[3]
		title = normalizeText(rawTitle)
		link = normalizeLink(rawLink)
		location = normalizeText(rawLocation)
		jobId = generateJobId(title, stableId)
		job = {
			"id": jobId,
			"title": title,
			"link": link,
			"location": location,
			"department": "",
			"jobType": "",
			"postedAt": "",
			"state": "open",
		}
		newJobs.append(job)
		index = index + 1
	return newJobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	htmlText = ""
	try:
		async with aiohttp.ClientSession() as session:
			response = await session.get(url, timeout=aiohttp.ClientTimeout(total=30))
			response.raise_for_status()
			htmlText = await response.text()
	except Exception as error:
		logger.warning("Failed to fetch %s: %s", companyName, error)
	jobs = parseJobsFromHtml(htmlText)
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