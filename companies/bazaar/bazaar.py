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


sourceUrl = "https://www.bazaartech.com/careers"
apiUrl = "https://api.manatal.com/open/v3/career-page/bazaar-technologies/jobs/?page_size=100"
requestTimeoutSeconds = 30
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
bazaarJsonPath = Path(__file__).with_name("bazaar.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, manatalId: str) -> str:
	hasStableId = manatalId != ""
	if hasStableId:
		raw = title + str(manatalId)
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def getJsonSync(url: str) -> dict:
	request = Request(url)
	request.add_header("User-Agent", userAgent)
	request.add_header("Accept", "application/json")
	response = urlopen(request, timeout=requestTimeoutSeconds)
	rawBody = response.read()
	data = json.loads(rawBody.decode("utf-8", errors="ignore"))
	return data


async def getJson(url: str) -> dict:
	data = await asyncio.to_thread(getJsonSync, url)
	return data


def buildJobLink(jobHash: str) -> str:
	if not jobHash:
		return sourceUrl
	link = f"https://www.bazaartech.com/careers#{jobHash}"
	return link


def parseJobPosting(posting: dict) -> dict[str, str]:
	manatalId = posting.get("id", "")
	jobHash = posting.get("hash", "")
	title = posting.get("position_name", "").strip()
	department = posting.get("organization_name", "").strip()
	location = ""

	locations = posting.get("locations", [])
	if locations and len(locations) > 0:
		locationObj = locations[0]
		locName = locationObj.get("name", "").strip()
		if locName:
			location = locName

	link = buildJobLink(jobHash)
	jobId = generateJobId(title, manatalId)

	record = {
		"id": jobId,
		"title": title,
		"link": link,
		"location": location,
		"department": department,
		"jobType": "",
		"postedAt": "",
		"state": "open",
	}
	return record


async def fetchState(url: str = apiUrl) -> dict[str, Any]:
	logger.info("Fetching Bazaar jobs from %s", url)
	allJobs: list[dict[str, str]] = []

	try:
		apiResponse = await getJson(url)
		results = apiResponse.get("results", [])
		jobIndex = 0
		while jobIndex < len(results):
			posting = results[jobIndex]
			job = parseJobPosting(posting)
			allJobs.append(job)
			jobIndex = jobIndex + 1
		logger.info("Parsed %d total Bazaar jobs", len(allJobs))
	except Exception as error:
		logger.exception("Failed to fetch Bazaar jobs: %s", error)
		allJobs = []

	fetchedAt = datetime.now(timezone.utc).isoformat()
	state = {
		"sourceUrl": sourceUrl,
		"fetchedAt": fetchedAt,
		"state": "open",
		"jobs": allJobs,
	}
	return state


def defaultSnapshot() -> dict[str, Any]:
	return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def loadExistingSnapshot() -> dict[str, Any]:
	if not bazaarJsonPath.exists():
		return defaultSnapshot()
	content = bazaarJsonPath.read_text(encoding="utf-8")
	if not content.strip():
		return defaultSnapshot()
	return json.loads(content)


def buildSnapshot(state: dict[str, Any], existingSnapshot: dict[str, Any]) -> dict[str, Any]:
	newJobs = state.get("jobs", [])
	oldJobs = existingSnapshot.get("jobs", [])

	suspiciousDrop = len(oldJobs) > 0 and len(newJobs) == 0
	if suspiciousDrop:
		logger.warning("Suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", len(oldJobs), len(newJobs))
		return dict(existingSnapshot)

	snapshot = dict(existingSnapshot)
	snapshot["sourceUrl"] = state.get("sourceUrl", sourceUrl)
	snapshot["fetchedAt"] = state.get("fetchedAt", "")
	snapshot["state"] = state.get("state", "open")
	snapshot["jobs"] = newJobs
	return snapshot


def writeSnapshot(snapshot: dict[str, Any]) -> None:
	output = json.dumps(snapshot, indent=2, ensure_ascii=False)
	bazaarJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = apiUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated Bazaar snapshot at %s", bazaarJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update Bazaar snapshot: %s", error)
		snapshot = buildSnapshot(defaultSnapshot(), existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		return snapshot


async def runMain() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--url", default=apiUrl)
	args = parser.parse_args()

	snapshot = await updateSnapshot(args.url)
	print(json.dumps(snapshot, indent=2, ensure_ascii=False))


if __name__ == "__main__":
	asyncio.run(runMain())