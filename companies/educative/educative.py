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


sourceUrl = "https://api.lever.co/v0/postings/educative?mode=json"
requestTimeoutSeconds = 30
educativeJsonPath = Path(__file__).with_name("educative.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, link: str) -> str:
	raw = title + link
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def parsePosting(posting: dict[str, Any]) -> dict[str, str] | None:
	title = (posting.get("text") or "").strip()
	link = (posting.get("hostedUrl") or "").strip()

	if not title or not link:
		return None

	categories = posting.get("categories", {})
	department = (categories.get("team") or categories.get("department") or "").strip()
	location = (categories.get("location") or "").strip()
	commitment = (categories.get("commitment") or "").strip()
	workplaceType = (posting.get("workplaceType") or "").strip()

	createdAtRaw = posting.get("createdAt")
	postedAt = ""
	if createdAtRaw:
		postedAtSeconds = createdAtRaw / 1000
		postedAtDatetime = datetime.fromtimestamp(postedAtSeconds, tz=timezone.utc)
		postedAt = postedAtDatetime.isoformat()

	jobId = generateJobId(title, link)

	record = {
		"id": jobId,
		"title": title,
		"link": link,
		"department": department,
		"location": location,
		"jobType": commitment,
		"workplaceType": workplaceType,
		"postedAt": postedAt,
		"state": "open",
	}
	return record


async def fetchPostings(url: str) -> list[dict[str, Any]]:
	timeout = aiohttp.ClientTimeout(total=requestTimeoutSeconds)
	async with aiohttp.ClientSession(timeout=timeout) as session:
		async with session.get(url) as response:
			response.raise_for_status()
			postings = await response.json()
			return postings


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching Educative jobs from %s", url)
	jobs: list[dict[str, str]] = []

	try:
		postings = await fetchPostings(url)
		postingIndex = 0
		while postingIndex < len(postings):
			currentPosting = postings[postingIndex]
			record = parsePosting(currentPosting)
			if record is not None:
				jobs.append(record)
			postingIndex = postingIndex + 1
		logger.info("Parsed %d total Educative jobs", len(jobs))
	except Exception as error:
		logger.exception("Failed to fetch Educative jobs: %s", error)
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
	if not educativeJsonPath.exists():
		return defaultSnapshot()

	content = educativeJsonPath.read_text(encoding="utf-8")
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
	educativeJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated Educative snapshot at %s", educativeJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update Educative snapshot: %s", error)
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
