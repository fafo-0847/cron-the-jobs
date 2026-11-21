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


sourceUrl = "https://api.webhr.co/api/careers/"
requestTimeoutSeconds = 30
tpsJsonPath = Path(__file__).with_name("tps.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, jobPostId: str) -> str:
	hasStableId = jobPostId != ""
	if hasStableId:
		raw = title + jobPostId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def buildJobLink(jobPostId: str) -> str:
	hasJobPostId = jobPostId != ""
	if not hasJobPostId:
		return ""
	link = f"https://tps.webhr.co/jobs/{jobPostId}"
	return link


async def fetchJobsFromApi() -> list[dict[str, str]]:
	jobs: list[dict[str, str]] = []

	payloadObject = {
		"o": "tps",
		"OpenJobPosts": {},
		"Settings": {},
	}
	params = {
		"r": "Web",
		"rt": "Data",
		"p": json.dumps(payloadObject),
	}

	timeout = aiohttp.ClientTimeout(total=requestTimeoutSeconds)
	async with aiohttp.ClientSession(timeout=timeout) as session:
		async with session.post(sourceUrl, params=params) as response:
			responseText = await response.text()

	payload = json.loads(responseText)
	apiError = payload.get("Error")
	if apiError:
		# Seen since Nov 2026: {"Status":0,"Error":"ORG_NOT_FOUND"}. The WebHR org "tps" was
		# removed; tpsworldwide.com/careers embeds the same (now dead) WebHR widget.
		raise ValueError(f"WebHR API error: {apiError} (TPS careers widget on tpsworldwide.com/careers is also empty)")
	data = payload.get("Data")
	if not isinstance(data, dict) or not isinstance(data.get("OpenJobPosts"), list):
		raise ValueError(f"unexpected WebHR payload: {responseText[:200]}")
	jobPosts = data["OpenJobPosts"]

	jobIndex = 0
	while jobIndex < len(jobPosts):
		item = jobPosts[jobIndex]

		title = str(item.get("JobTitle") or "").strip()
		jobPostId = str(item.get("JobPostId") or "").strip()
		station = str(item.get("Stations") or "").strip()
		country = str(item.get("Country") or "").strip()
		department = str(item.get("Departments") or "").strip()
		jobType = str(item.get("JobType") or "").strip()
		postedAt = str(item.get("JobPostClosingDate") or "").strip()

		locationParts: list[str] = []
		if station:
			locationParts.append(station)
		if country:
			locationParts.append(country)
		location = ", ".join(locationParts)

		link = buildJobLink(jobPostId)
		jobId = generateJobId(title, jobPostId)

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
	logger.info("Fetching TPS jobs from %s", url)
	allJobs: list[dict[str, str]] = []

	try:
		allJobs = await fetchJobsFromApi()
		logger.info("Parsed %d total TPS jobs", len(allJobs))
	except Exception as error:
		logger.exception("Failed to fetch TPS jobs: %s", error)
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
	if not tpsJsonPath.exists():
		return defaultSnapshot()

	content = tpsJsonPath.read_text(encoding="utf-8")
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
	tpsJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated TPS snapshot at %s", tpsJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update TPS snapshot: %s", error)
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
