import hashlib
import json
import logging
import datetime
import re
from pathlib import Path
from typing import Any

import html as htmlLib

import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("persivia")

sourceUrl = "https://persivia.com/careers"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "persivia.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def extractStableId(containerClass: str) -> str:
	match = re.search(r"post-(\d+)", containerClass)
	hasMatch = match is not None
	if hasMatch:
		return match.group(1)
	return ""


def normalizeText(rawText) -> str:
	isNone = rawText is None
	if isNone:
		return ""
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


jobListPattern = re.compile(r'<ul class="job-list">(.*?)</ul>', re.S)
jobTitlePattern = re.compile(r'<span class="job-list__title">(.*?)</span>', re.S)
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def parseJobList(html: str) -> list[dict[str, str]]:
	"""Parses the Nov 2026 site: a plain <ul class="job-list"> of titles, applications go
	through one HubSpot form on the same page (no per-job pages or locations)."""
	listMatch = jobListPattern.search(html)
	if listMatch is None:
		raise ValueError("persivia: job list (ul.job-list) not found (layout changed)")
	jobs: list[dict[str, str]] = []
	for titleMatch in jobTitlePattern.finditer(listMatch.group(1)):
		title = normalizeText(htmlLib.unescape(re.sub(r"<[^>]+>", "", titleMatch.group(1))))
		if title == "":
			continue
		jobs.append({
			"id": generateJobId(title, ""),
			"title": title,
			"link": sourceUrl + "#openings",
			"location": "",
			"department": "Persivia Inc",
			"jobType": "",
			"postedAt": "",
			"state": "open",
		})
	return jobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	confirmedEmpty = False
	try:
		timeout = aiohttp.ClientTimeout(total=30)
		async with aiohttp.ClientSession(headers={"User-Agent": userAgent}, timeout=timeout) as session:
			async with session.get(url) as response:
				response.raise_for_status()
				html = await response.text()
		jobs = parseJobList(html)
		confirmedEmpty = len(jobs) == 0
	except Exception as error:
		logger.exception("persivia: fetchState failed: %s", error)
	state = {"jobs": jobs, "state": "open", "confirmedEmpty": confirmedEmpty}
	return state


def loadExistingSnapshot() -> dict[str, Any]:
	try:
		fileExists = snapshotPath.exists()
		if not fileExists:
			return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}
		rawText = snapshotPath.read_text(encoding="utf-8")
		snapshot = json.loads(rawText)
		return snapshot
	except Exception as error:
		logger.exception("persivia: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("persivia: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
		return dict(existingSnapshot)
	fetchedAt = datetime.datetime.now(datetime.timezone.utc).isoformat()
	snapshot = {
		"sourceUrl": sourceUrl,
		"fetchedAt": fetchedAt,
		"state": state.get("state", "open"),
		"jobs": newJobs,
	}
	return snapshot


def writeSnapshot(snapshot: dict) -> None:
	try:
		snapshotText = json.dumps(snapshot, indent=2, ensure_ascii=False)
		snapshotPath.write_text(snapshotText, encoding="utf-8")
	except Exception as error:
		logger.exception("persivia: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("persivia: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())