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
logger = logging.getLogger("phaedrasolutions")

sourceUrl = "https://www.phaedrasolutions.com/company/careers"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "phaedrasolutions.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def extractStableId(href: str) -> str:
	segments = href.strip("/").split("/")
	hasSegments = len(segments) > 0
	if hasSegments:
		stableId = segments[-1]
	else:
		stableId = ""
	return stableId


def normalizeText(rawText) -> str:
	isNone = rawText is None
	if isNone:
		return ""
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


# Nov 2026: site moved from Webflow (.career-card) to WordPress + Elementor. Each job is an
# Elementor loop item tagged "type-job department-<slug>" with widgets jc0loc1 (location),
# jc0exp1 (experience), jc0ttl1 (title) and jc0btn1 (ClickUp apply link). Server-rendered.
loopItemSplitPattern = re.compile(r'<div data-elementor-type="loop-item"')
jobClassPattern = re.compile(r'class="[^"]*\btype-job\b[^"]*"')
departmentClassPattern = re.compile(r"\bdepartment-([a-z0-9-]+)")
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def widgetText(itemHtml: str, widgetId: str) -> str:
	match = re.search(r'elementor-element-' + widgetId + r'\b.*?<(?:p|h\d)[^>]*>(.*?)</(?:p|h\d)>', itemHtml, re.S)
	if match is None:
		return ""
	return normalizeText(htmlLib.unescape(re.sub(r"<[^>]+>", "", match.group(1))))


def widgetHref(itemHtml: str, widgetId: str) -> str:
	match = re.search(r'elementor-element-' + widgetId + r'\b.*?<a[^>]*href="([^"]+)"', itemHtml, re.S)
	return htmlLib.unescape(match.group(1)) if match else ""


def parseJobsHtml(html: str) -> list[dict[str, Any]]:
	jobs = []
	for chunk in loopItemSplitPattern.split(html)[1:]:
		header = chunk[:600]
		classMatch = jobClassPattern.search(header)
		if classMatch is None:
			continue
		title = widgetText(chunk, "jc0ttl1")
		if title == "":
			continue
		departmentMatch = departmentClassPattern.search(classMatch.group(0))
		department = departmentMatch.group(1).replace("-", " ").title() if departmentMatch else ""
		href = widgetHref(chunk, "jc0btn1")
		jobs.append({
			"id": generateJobId(title, extractStableId(href)),
			"title": title,
			"link": href,
			"location": widgetText(chunk, "jc0loc1"),
			"department": department,
			"jobType": "",
			"experience": widgetText(chunk, "jc0exp1"),
			"postedAt": "",
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
		jobs = parseJobsHtml(html)
		if len(jobs) == 0:
			logger.error("phaedrasolutions: no Elementor job loop items found (layout changed?)")
	except Exception as error:
		logger.exception("phaedrasolutions: fetchState failed: %s", error)
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
		logger.exception("phaedrasolutions: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("phaedrasolutions: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("phaedrasolutions: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("phaedrasolutions: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())