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

sourceUrl = "https://boards-api.greenhouse.io/v1/boards/careem/departments"
requestTimeoutSeconds = 30
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
currentFile = Path(__file__)
careemJsonPath = currentFile.with_name("careem.json")
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
			rawError = exc.read()
			errorBody = rawError.decode("utf-8", errors="ignore")
			truncatedBody = errorBody[:500]
			logger.error("API error body: %s", truncatedBody)
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
	encoded = raw.encode("utf-8")
	hasher = hashlib.md5(encoded)
	jobId = hasher.hexdigest()
	return jobId


def parseJobPosting(job: dict, departmentName: str) -> dict[str, str]:
	title = job.get("title", "")
	link = job.get("absolute_url", "")
	locationObj = job.get("location", {})
	location = ""
	if isinstance(locationObj, dict):
		location = locationObj.get("name", "")
	postedAt = job.get("updated_at", "")
	jobId = generateJobId(title, link)
	record = {
		"id": jobId,
		"title": title,
		"link": link,
		"location": location,
		"department": departmentName,
		"postedAt": postedAt,
		"state": "open",
	}
	return record


async def fetchAllJobs() -> list[dict[str, str]]:
	allJobs = []
	apiPage = await getJson(sourceUrl)
	departmentsList = apiPage.get("departments", [])
	deptCount = len(departmentsList)
	deptIndex = 0
	while deptIndex < deptCount:
		departmentObj = departmentsList[deptIndex]
		departmentName = departmentObj.get("name", "")
		jobsList = departmentObj.get("jobs", [])
		jobsCount = len(jobsList)
		jobIndex = 0
		while jobIndex < jobsCount:
			jobObj = jobsList[jobIndex]
			parsedJob = parseJobPosting(jobObj, departmentName)
			allJobs.append(parsedJob)
			jobIndex += 1
		deptIndex += 1
	return allJobs


async def fetchState() -> dict[str, Any]:
	logger.info("Fetching Careem jobs from %s", sourceUrl)
	try:
		allJobs = await fetchAllJobs()
		logger.info("Parsed %d Careem jobs", len(allJobs))
	except Exception as error:
		logger.exception("Failed to fetch Careem jobs: %s", error)
		allJobs = []
	utcZone = timezone.utc
	nowTime = datetime.now(utcZone)
	fetchedAt = nowTime.isoformat()
	stateObj = {
		"sourceUrl": sourceUrl,
		"fetchedAt": fetchedAt,
		"state": "open",
		"jobs": allJobs,
	}
	return stateObj


def defaultSnapshot() -> dict[str, Any]:
	snapshotObj = {
		"sourceUrl": sourceUrl,
		"fetchedAt": "",
		"state": "open",
		"jobs": [],
	}
	return snapshotObj


def loadExistingSnapshot() -> dict[str, Any]:
	exists = careemJsonPath.exists()
	if not exists:
		defaultSnap = defaultSnapshot()
		return defaultSnap
	content = careemJsonPath.read_text(encoding="utf-8")
	stripped = content.strip()
	if not stripped:
		defaultSnap = defaultSnapshot()
		return defaultSnap
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
	fileContent = output + "\n"
	careemJsonPath.write_text(fileContent, encoding="utf-8")


async def updateSnapshot() -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState()
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated Careem snapshot at %s", careemJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update Careem snapshot: %s", error)
		defaultSnap = defaultSnapshot()
		snapshot = buildSnapshot(defaultSnap, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		return snapshot


async def runMain() -> None:
	cmdParser = argparse.ArgumentParser()
	cmdParser.parse_args()
	snapshot = await updateSnapshot()
	jsonOutput = json.dumps(snapshot, indent=2, ensure_ascii=False)
	print(jsonOutput)


if __name__ == "__main__":
	asyncio.run(runMain())
