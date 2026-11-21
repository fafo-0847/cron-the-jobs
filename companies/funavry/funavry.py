import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

import html as htmlLib
import re

import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("funavry")

sourceUrl = "https://www.funavry.com/careers"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "funavry.json"


def generateJobId(title: str, location: str, jobType: str) -> str:
	raw = title + "|" + location + "|" + jobType
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def parseDetailLine(text: str) -> dict[str, str]:
	details = {}
	normalized = text.replace("\xa0", " ").strip()
	parts = normalized.split("|")
	index = 0
	while index < len(parts):
		chunk = parts[index].strip()
		hasColon = ":" in chunk
		if hasColon:
			key, value = chunk.split(":", 1)
			details[key.strip().lower()] = value.strip()
		index = index + 1
	return details


# Nov 2026: career.html is a 404; the Next.js site lists roles at /careers as
# <a href="/careers/<slug>"> cards: <h3> title, work-mode pill, "Posted <date>",
# lucide map-pin span (location) and briefcase span (job type). Server-rendered.
siteUrl = "https://www.funavry.com"
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
roleCardPattern = re.compile(r'<a href="(?P<href>/careers/[a-z0-9-]+)"[^>]*>(?P<body>.*?)</a>', re.S)
titlePattern = re.compile(r"<h3[^>]*>(.*?)</h3>", re.S)
workModePattern = re.compile(r"</h3><span[^>]*>(.*?)</span>", re.S)
postedPattern = re.compile(r">Posted (?:<!-- -->)?([^<]+)<", re.S)
iconTextPattern = re.compile(r'lucide-(?P<icon>map-pin|briefcase)[^"]*".*?</svg>(?P<text>[^<]*)</span>', re.S)


def cleanText(fragment: str) -> str:
	text = htmlLib.unescape(re.sub(r"<[^>]+>", " ", fragment))
	return re.sub(r"\s+", " ", text).replace("\xa0", " ").strip()


def parseRolesHtml(html: str) -> list[dict[str, Any]]:
	jobs = []
	seenLinks: set[str] = set()
	for cardMatch in roleCardPattern.finditer(html):
		body = cardMatch.group("body")
		titleMatch = titlePattern.search(body)
		title = cleanText(titleMatch.group(1)) if titleMatch else ""
		link = siteUrl + cardMatch.group("href")
		if title == "" or link in seenLinks:
			continue
		seenLinks.add(link)
		icons = {match.group("icon"): cleanText(match.group("text")) for match in iconTextPattern.finditer(body)}
		location = re.sub(r"\s+,", ",", icons.get("map-pin", ""))
		jobType = icons.get("briefcase", "")
		workModeMatch = workModePattern.search(body)
		postedMatch = postedPattern.search(body)
		jobs.append({
			"id": generateJobId(title, location, jobType),
			"title": title,
			"link": link,
			"location": location,
			"department": "",
			"jobType": jobType,
			"workMode": cleanText(workModeMatch.group(1)) if workModeMatch else "",
			"postedAt": cleanText(postedMatch.group(1)) if postedMatch else "",
			"state": "open",
		})
	return jobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		timeout = aiohttp.ClientTimeout(total=30)
		async with aiohttp.ClientSession(headers={"User-Agent": userAgent}, timeout=timeout) as session:
			async with session.get(url) as response:
				response.raise_for_status()
				html = await response.text()
		jobs = parseRolesHtml(html)
		if len(jobs) == 0:
			logger.error("funavry: no /careers/<slug> role cards found (layout changed?)")
	except Exception as error:
		logger.exception("funavry: fetchState failed: %s", error)
	state = {"jobs": jobs, "state": "open"}
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
		logger.exception("funavry: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("funavry: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("funavry: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("funavry: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())