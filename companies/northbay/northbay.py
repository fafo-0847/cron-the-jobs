from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp


sourceUrl = "https://api.resumatorapi.com/v1/jobs/status/open?apikey=9xmcuwVUT7G1mbVPmcL25yZ74FLkAqq8"
requestTimeoutSeconds = 30
northbayJsonPath = Path(__file__).with_name("northbay.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, apiJobId: str) -> str:
	hasStableId = apiJobId != ""
	if hasStableId:
		raw = title + apiJobId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def buildJobLink(boardCode: str, apiJobId: str) -> str:
	hasBoardCode = boardCode != "" and apiJobId != ""
	if not hasBoardCode:
		return ""
	link = f"https://northbay.resumatorsite.com/apply/{boardCode}/{apiJobId}"
	return link


def parseJobsFromApi(apiResponse: list) -> list[dict[str, str]]:
	jobs: list[dict[str, str]] = []

	jobIndex = 0
	while jobIndex < len(apiResponse):
		item = apiResponse[jobIndex]

		title = str(item.get("title") or "").strip()
		city = str(item.get("city") or "").strip()
		country = str(item.get("country_id") or "").strip()
		department = str(item.get("department") or "").strip()
		jobType = str(item.get("type") or "").strip()
		postedAt = str(item.get("original_open_date") or "").strip()
		apiJobId = str(item.get("id") or "").strip()
		boardCode = str(item.get("board_code") or "").strip()

		locationParts: list[str] = []
		if city:
			locationParts.append(city)
		if country:
			locationParts.append(country)
		location = ", ".join(locationParts)

		link = buildJobLink(boardCode, apiJobId)
		jobId = generateJobId(title, apiJobId)

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


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching NorthBay jobs from %s", url)
	allJobs: list[dict[str, str]] = []

	try:
		timeout = aiohttp.ClientTimeout(total=requestTimeoutSeconds)
		async with aiohttp.ClientSession(timeout=timeout) as session:
			async with session.get(url) as response:
				if response.status == 200:
					apiData = await response.json()
					allJobs = parseJobsFromApi(apiData)
					logger.info("Parsed %d total NorthBay jobs", len(allJobs))
				else:
					logger.warning("API returned status %d", response.status)
					allJobs = []
	except Exception as error:
		logger.exception("Failed to fetch NorthBay jobs: %s", error)
		allJobs = []

	fetchedAt = datetime.now(timezone.utc).isoformat()
	state = {
		"sourceUrl": url,
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
	if not northbayJsonPath.exists():
		return defaultSnapshot()

	content = northbayJsonPath.read_text(encoding="utf-8")
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
	northbayJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated NorthBay snapshot at %s", northbayJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update NorthBay snapshot: %s", error)
		snapshot = buildSnapshot(defaultSnapshot(url), existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		return snapshot


async def runMain() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--url", default=sourceUrl)
	args = parser.parse_args()

	snapshot = await updateSnapshot(args.url)
	output = json.dumps(snapshot, indent=2, ensure_ascii=False)
	print(output)


if __name__ == "__main__":
	asyncio.run(runMain())
