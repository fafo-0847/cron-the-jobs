from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import aiohttp


sourceUrl = "https://carbonteq.com/careers/"
apiUrl = "https://api.resumatorapi.com/v1/jobs/status/open?apikey=Y5uJhnJlBk1AdkHa5e0G1tie1v0ARW8d"
boardCode = "ImhgOLzP8U"
requestTimeoutSeconds = 60
carbonteqJsonPath = Path(__file__).with_name("carbonteq.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, jobApiId: str) -> str:
	raw = title + jobApiId
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def buildJobLink(boardCode: str, jobApiId: str) -> str:
	link = f"https://carbonteq.resumatorsite.com/apply/{boardCode}/{jobApiId}"
	return link


def parseJobsFromApi(apiResponse: list) -> list[dict[str, str]]:
	jobs: list[dict[str, str]] = []

	jobIndex = 0
	while jobIndex < len(apiResponse):
		jobData = apiResponse[jobIndex]

		jobApiId = jobData.get("id", "")
		title = jobData.get("title", "").strip()
		country = jobData.get("country_id", "").strip()
		city = jobData.get("city", "").strip()
		state = jobData.get("state", "").strip()
		department = jobData.get("department", "").strip()
		jobType = jobData.get("type", "").strip()
		postedAt = jobData.get("original_open_date", "").strip()

		locationParts: list[str] = []
		if city:
			locationParts.append(city)
		if state:
			locationParts.append(state)
		if country:
			locationParts.append(country)
		location = ", ".join(locationParts)

		link = buildJobLink(boardCode, jobApiId)

		if not title or not jobApiId:
			jobIndex = jobIndex + 1
			continue

		jobId = generateJobId(title, jobApiId)

		record = {
			"id": jobId,
			"title": title,
			"link": link,
			"location": location,
			"department": department,
			"jobType": jobType,
			"postedAt": postedAt,
			"state": "open",
		}
		jobs.append(record)
		jobIndex = jobIndex + 1

	return jobs


async def fetchState(url: str = apiUrl) -> dict[str, Any]:
	logger.info("Fetching CarbonTeq jobs from API %s", url)
	allJobs: list[dict[str, str]] = []

	try:
		timeout = aiohttp.ClientTimeout(total=requestTimeoutSeconds)
		async with aiohttp.ClientSession(timeout=timeout) as session:
			async with session.get(url) as response:
				if response.status == 200:
					apiData = await response.json()
					allJobs = parseJobsFromApi(apiData)
					logger.info("Parsed %d total CarbonTeq jobs", len(allJobs))
				else:
					logger.warning("API returned status %d", response.status)
					allJobs = []
	except Exception as error:
		logger.exception("Failed to fetch CarbonTeq jobs from API: %s", error)
		allJobs = []

	fetchedAt = datetime.now(timezone.utc).isoformat()
	state = {
		"sourceUrl": sourceUrl,
		"fetchedAt": fetchedAt,
		"state": "open",
		"jobs": allJobs,
	}
	return state


def defaultSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	snapshot = {
		"sourceUrl": url,
		"fetchedAt": "",
		"state": "open",
		"jobs": [],
	}
	return snapshot


def loadExistingSnapshot() -> dict[str, Any]:
	if not carbonteqJsonPath.exists():
		return defaultSnapshot()

	content = carbonteqJsonPath.read_text(encoding="utf-8")
	if not content.strip():
		return defaultSnapshot()

	data = json.loads(content)
	return data


def buildSnapshot(state: dict[str, Any], existingSnapshot: dict[str, Any]) -> dict[str, Any]:
	newJobs = state.get("jobs", [])
	oldJobs = existingSnapshot.get("jobs", [])

	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)

	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("Suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
		snapshot = dict(existingSnapshot)
		return snapshot

	snapshot = dict(existingSnapshot)
	snapshot["sourceUrl"] = state.get("sourceUrl", sourceUrl)
	snapshot["fetchedAt"] = state.get("fetchedAt", "")
	snapshot["state"] = state.get("state", "open")
	snapshot["jobs"] = newJobs
	return snapshot


def writeSnapshot(snapshot: dict[str, Any]) -> None:
	output = json.dumps(snapshot, indent=2, ensure_ascii=False)
	carbonteqJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = apiUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated CarbonTeq snapshot at %s", carbonteqJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update CarbonTeq snapshot: %s", error)
		snapshot = buildSnapshot(defaultSnapshot(sourceUrl), existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		return snapshot


async def runMain() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--url", default=apiUrl)
	args = parser.parse_args()

	snapshot = await updateSnapshot(args.url)
	output = json.dumps(snapshot, indent=2, ensure_ascii=False)
	print(output)


if __name__ == "__main__":
	asyncio.run(runMain())
