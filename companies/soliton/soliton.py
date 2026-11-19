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


sourceUrl = "https://www.solitontechnologies.com/backend/public/api/getJobs"
requestTimeoutSeconds = 30
solitonJsonPath = Path(__file__).with_name("soliton.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, jobId: int) -> str:
	raw = title + str(jobId)
	hashedId = hashlib.md5(raw.encode()).hexdigest()
	return hashedId


def buildJobLink(jobId: int) -> str:
	link = f"https://www.solitontechnologies.com/careers/{jobId}"
	return link


def parseJob(job: dict[str, Any]) -> dict[str, str] | None:
	title = (job.get("job_title") or "").strip()
	jobId = job.get("id")

	if not title or jobId is None:
		return None

	link = buildJobLink(jobId)
	location = (job.get("job_location") or "").strip()
	jobType = job.get("job_type")
	jobTypeStr = str(jobType) if jobType is not None else ""

	hashedId = generateJobId(title, jobId)

	record = {
		"id": hashedId,
		"title": title,
		"link": link,
		"location": location,
		"department": "",
		"jobType": jobTypeStr,
		"postedAt": "",
		"state": "open",
	}
	return record


async def fetchJobs(url: str) -> dict[str, Any]:
	timeout = aiohttp.ClientTimeout(total=requestTimeoutSeconds)
	async with aiohttp.ClientSession(timeout=timeout) as session:
		async with session.get(url) as response:
			response.raise_for_status()
			data = await response.json()
			return data


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching Soliton jobs from %s", url)
	jobs: list[dict[str, str]] = []

	try:
		rawResponse = await fetchJobs(url)
		jobsList = rawResponse.get("jobs", [])
		jobIndex = 0
		while jobIndex < len(jobsList):
			currentJob = jobsList[jobIndex]
			record = parseJob(currentJob)
			if record is not None:
				jobs.append(record)
			jobIndex = jobIndex + 1
		logger.info("Parsed %d total Soliton jobs", len(jobs))
	except Exception as error:
		logger.exception("Failed to fetch Soliton jobs: %s", error)
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
	if not solitonJsonPath.exists():
		return defaultSnapshot()

	content = solitonJsonPath.read_text(encoding="utf-8")
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
	solitonJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated Soliton snapshot at %s", solitonJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update Soliton snapshot: %s", error)
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
