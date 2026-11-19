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


sourceUrl = "https://api.resumatorapi.com/v1/jobs?apikey=jB0b57gnKdU9rqBWvqQpxzITAPrHUFaz"
requestTimeoutSeconds = 30
tenpearlsJsonPath = Path(__file__).with_name("10pearls.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, link: str) -> str:
	raw = title + link
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def buildJobLink(boardCode: str, jobId: str) -> str:
	link = f"https://10pearls.resumatorsite.com/apply/{boardCode}/{jobId}"
	return link


def parseJob(job: dict[str, Any]) -> dict[str, str] | None:
	title = (job.get("title") or "").strip()
	jobId = (job.get("id") or "").strip()

	if not title or not jobId:
		return None

	boardCode = (job.get("board_code") or "").strip()
	link = buildJobLink(boardCode, jobId) if boardCode else ""

	if not link:
		return None

	country = (job.get("country_id") or "").strip()
	city = (job.get("city") or "").strip()
	locationParts = []
	if city:
		locationParts.append(city)
	if country:
		locationParts.append(country)
	location = ", ".join(locationParts)

	department = (job.get("department") or "").strip()
	jobType = (job.get("type") or "").strip()
	postedAt = (job.get("original_open_date") or "").strip()

	hashInput = title + link
	hashedId = generateJobId(title, link)

	record = {
		"id": hashedId,
		"title": title,
		"link": link,
		"location": location,
		"department": department,
		"jobType": jobType,
		"postedAt": postedAt,
		"state": "open",
	}
	return record


async def fetchJobs(url: str) -> list[dict[str, Any]]:
	timeout = aiohttp.ClientTimeout(total=requestTimeoutSeconds)
	async with aiohttp.ClientSession(timeout=timeout) as session:
		async with session.get(url) as response:
			response.raise_for_status()
			jobs = await response.json()
			return jobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching 10Pearls jobs from %s", url)
	jobs: list[dict[str, str]] = []

	try:
		rawJobs = await fetchJobs(url)
		jobIndex = 0
		while jobIndex < len(rawJobs):
			currentJob = rawJobs[jobIndex]
			record = parseJob(currentJob)
			if record is not None:
				jobs.append(record)
			jobIndex = jobIndex + 1
		logger.info("Parsed %d total 10Pearls jobs", len(jobs))
	except Exception as error:
		logger.exception("Failed to fetch 10Pearls jobs: %s", error)
		jobs = []

	fetchedAt = datetime.now(timezone.utc).isoformat()
	state = {
		"sourceUrl": url,
		"fetchedAt": fetchedAt,
		"state": "open",
		"jobs": jobs,
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
	if not tenpearlsJsonPath.exists():
		return defaultSnapshot()

	content = tenpearlsJsonPath.read_text(encoding="utf-8")
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
	tenpearlsJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated 10Pearls snapshot at %s", tenpearlsJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update 10Pearls snapshot: %s", error)
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
