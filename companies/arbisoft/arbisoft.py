from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

sourceUrl = "https://arbisoft.hirestream.io/api/v1/jobs/published-jobs/?timezone=Asia%2FKarachi&offset=0&limit=20&order=featured"
requestTimeoutSeconds = 30
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
arbisoftJsonPath = Path(__file__).with_name("arbisoft.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def getJsonSync(url: str) -> dict:
	request = Request(url)
	request.add_header("User-Agent", userAgent)
	request.add_header("Accept", "application/json, text/plain, */*")
	
	try:
		response = urlopen(request, timeout=requestTimeoutSeconds)
	except Exception as exc:
		import urllib.error
		if isinstance(exc, urllib.error.HTTPError):
			errorBody = exc.read().decode("utf-8", errors="ignore")
			logger.error("API error body: %s", errorBody[:500])
		raise
		
	rawBody = response.read()
	text = rawBody.decode("utf-8", errors="ignore")
	data = json.loads(text)
	return data


async def getJson(url: str) -> dict:
	data = await asyncio.to_thread(getJsonSync, url)
	return data


def generateJobId(title: str, link: str) -> str:
	raw = title + link
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def buildJobLink(uuid: str) -> str:
	if not uuid:
		return ""
	link = f"https://arbisoft.hirestream.io/jobs/{uuid}"
	return link


def parseJobPosting(posting: dict) -> dict[str, str]:
	title = posting.get("title", "")
	department = posting.get("department", "")
	location = posting.get("location", "")
	modified = posting.get("modified", "")
	uuid = posting.get("uuid", "")
	
	link = buildJobLink(uuid)
	jobId = generateJobId(title, link)

	record = {
		"id": jobId,
		"title": title,
		"link": link,
		"location": location,
		"department": department,
		"postedAt": modified,
		"state": "open",
	}
	return record


async def fetchAllJobs() -> list[dict[str, str]]:
	jobs: list[dict[str, str]] = []
	nextUrl = sourceUrl

	while nextUrl:
		logger.info("Fetching API page: %s", nextUrl)
		page = await getJson(nextUrl)
		postings = page.get("results", [])
		for posting in postings:
			job = parseJobPosting(posting)
			jobs.append(job)
		
		nextUrl = page.get("next")

	return jobs


async def fetchState() -> dict[str, Any]:
	logger.info("Fetching Arbisoft jobs from %s", sourceUrl)
	try:
		jobs = await fetchAllJobs()
		logger.info("Parsed %d Arbisoft jobs", len(jobs))
	except Exception as error:
		logger.exception("Failed to fetch Arbisoft jobs: %s", error)
		jobs = []

	fetchedAt = datetime.now(timezone.utc).isoformat()
	state = {
		"sourceUrl": sourceUrl,
		"fetchedAt": fetchedAt,
		"state": "open",
		"jobs": jobs,
	}
	return state


def defaultSnapshot() -> dict[str, Any]:
	snapshot = {
		"sourceUrl": sourceUrl,
		"fetchedAt": "",
		"state": "open",
		"jobs": [],
	}
	return snapshot


def loadExistingSnapshot() -> dict[str, Any]:
	if not arbisoftJsonPath.exists():
		return defaultSnapshot()

	content = arbisoftJsonPath.read_text(encoding="utf-8")
	if not content.strip():
		return defaultSnapshot()

	data = json.loads(content)
	return data


def buildSnapshot(state: dict[str, Any], existingSnapshot: dict[str, Any]) -> dict[str, Any]:
	snapshot = dict(existingSnapshot)
	snapshot["sourceUrl"] = state.get("sourceUrl", sourceUrl)
	snapshot["fetchedAt"] = state.get("fetchedAt", "")
	snapshot["state"] = state.get("state", "open")
	snapshot["jobs"] = state.get("jobs", [])
	return snapshot


def writeSnapshot(snapshot: dict[str, Any]) -> None:
	output = json.dumps(snapshot, indent=2, ensure_ascii=False)
	arbisoftJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot() -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState()
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated Arbisoft snapshot at %s", arbisoftJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update Arbisoft snapshot: %s", error)
		snapshot = buildSnapshot(defaultSnapshot(), existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		return snapshot


async def runMain() -> None:
	parser = argparse.ArgumentParser()
	parser.parse_args()

	snapshot = await updateSnapshot()
	output = json.dumps(snapshot, indent=2, ensure_ascii=False)
	print(output)


if __name__ == "__main__":
	asyncio.run(runMain())
