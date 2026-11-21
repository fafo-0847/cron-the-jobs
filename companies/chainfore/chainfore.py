import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
import html as htmlLib
import re

import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chainfore")

sourceUrl = "https://www.chainfore.com/careers"
snapshotPath = Path(__file__).parent / "chainfore.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def loadExistingSnapshot() -> dict[str, Any]:
	snapshotExists = snapshotPath.exists()
	if snapshotExists:
		fileContent = snapshotPath.read_text(encoding="utf-8")
		existingSnapshot = json.loads(fileContent)
	else:
		existingSnapshot = dict(sourceUrl=sourceUrl, fetchedAt="", state="unknown", jobs=[])
	return existingSnapshot


noOpeningsPattern = re.compile(r"No roles are open|no open (?:roles|positions)|no openings", re.I)
openRolesSectionPattern = re.compile(r">\s*Open roles\s*</h2>(.*?)(?:<section|</main>)", re.S | re.I)
roleHeadingPattern = re.compile(r"<(h3|h4)[^>]*>(.*?)</\1>", re.S | re.I)
tagPattern = re.compile(r"<[^>]+>")
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def stripTags(fragment: str) -> str:
	text = htmlLib.unescape(tagPattern.sub(" ", fragment))
	return normalizeText(text)


def parseOpenRoles(html: str) -> dict[str, Any]:
	"""Parses the 'Open roles' section of the Nov 2026 site.

	Returns {"jobs": [...], "confirmedEmpty": bool}. Raises ValueError when the
	section is missing, so a future redesign is reported instead of silently
	looking like 'no jobs'.
	"""
	sectionMatch = openRolesSectionPattern.search(html)
	if sectionMatch is None:
		raise ValueError("chainfore: 'Open roles' section not found (layout changed)")
	sectionHtml = sectionMatch.group(1)
	sectionText = stripTags(sectionHtml)
	if noOpeningsPattern.search(sectionText):
		return {"jobs": [], "confirmedEmpty": True}
	jobs: list[dict[str, Any]] = []
	for headingMatch in roleHeadingPattern.finditer(sectionHtml):
		title = stripTags(headingMatch.group(2))
		if title == "":
			continue
		jobs.append({
			"id": generateJobId(title, ""),
			"title": title,
			"link": sourceUrl,
			"location": "",
			"department": "",
			"jobType": "",
			"postedAt": "",
			"state": "open",
		})
	if len(jobs) == 0:
		raise ValueError(f"chainfore: roles section present but no role headings parsed: {sectionText[:200]}")
	return {"jobs": jobs, "confirmedEmpty": False}


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	confirmedEmpty = False
	errorOccurred = False
	try:
		timeout = aiohttp.ClientTimeout(total=45)
		async with aiohttp.ClientSession(headers={"User-Agent": userAgent}, timeout=timeout) as session:
			async with session.get(url) as response:
				response.raise_for_status()
				html = await response.text()
		result = parseOpenRoles(html)
		jobs = result["jobs"]
		confirmedEmpty = result["confirmedEmpty"]
	except Exception as fetchException:
		errorOccurred = True
		logger.exception("Failed to fetch chainfore jobs: %s", fetchException)
	stateResult = "error" if errorOccurred else "open"
	state = dict(jobs=jobs, state=stateResult, confirmedEmpty=confirmedEmpty)
	return state


def normalizeText(text: str) -> str:
	normalized = text.replace("\xa0", " ").strip()
	normalized = " ".join(normalized.split())
	return normalized


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	newJobs = state.get("jobs", [])
	oldJobs = existingSnapshot.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("Suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
		return dict(existingSnapshot)
	fetchedAt = datetime.datetime.now(datetime.timezone.utc).isoformat()
	snapshot = dict(
		sourceUrl=sourceUrl,
		fetchedAt=fetchedAt,
		state=state.get("state", "unknown"),
		jobs=newJobs,
	)
	return snapshot


def writeSnapshot(snapshot: dict) -> None:
	snapshotJson = json.dumps(snapshot, indent=2)
	snapshotPath.write_text(snapshotJson, encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("chainfore: wrote %d jobs", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())