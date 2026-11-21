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
logger = logging.getLogger("devntech")

sourceUrl = "https://www.devntech.com/careers"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "devntech.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def extractStableId(href: str) -> str:
	slug = href.strip("/").split("/")[-1]
	tokens = slug.split("-")
	hasTokens = len(tokens) > 0
	if hasTokens:
		lastToken = tokens[-1]
	else:
		lastToken = ""
	isNumeric = lastToken.isdigit()
	if isNumeric:
		stableId = lastToken
	else:
		stableId = slug
	return stableId


def normalizeText(rawText) -> str:
	isNone = rawText is None
	if isNone:
		return ""
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


def stripExperienceLabel(rawText: str) -> str:
	normalized = normalizeText(rawText)
	prefix = "Experience:"
	hasPrefix = normalized.startswith(prefix)
	if hasPrefix:
		normalized = normalized[len(prefix):].strip()
	return normalized


rolesSectionPattern = re.compile(r'<section id="roles"[^>]*>(.*?)</section>', re.S)
roleCardSplitPattern = re.compile(r'<div class="[^"]*\bflex h-full flex-col\b[^"]*">')
paragraphPattern = re.compile(r"<p[^>]*>(.*?)</p>", re.S)
tagSpanPattern = re.compile(r'<span class="rounded-md[^"]*">(.*?)</span>', re.S)
applyLinkPattern = re.compile(r'href="(https://[^"]*\.odoo\.com/jobs/[^"]+)"')
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def cleanHtmlText(fragment: str) -> str:
	return normalizeText(htmlLib.unescape(re.sub(r"<[^>]+>", " ", fragment)))


def parseRolesHtml(html: str) -> list[dict[str, Any]]:
	"""2026 layout: each role card is <div class="flex h-full flex-col ..."> with a title <p>,
	tag <span>s (work mode, experience), a description <p> and an Odoo apply link."""
	sectionMatch = rolesSectionPattern.search(html)
	if sectionMatch is None:
		raise ValueError("devntech: <section id=roles> not found (layout changed)")
	jobs: list[dict[str, Any]] = []
	cardChunks = roleCardSplitPattern.split(sectionMatch.group(1))[1:]
	for chunk in cardChunks:
		linkMatch = applyLinkPattern.search(chunk)
		paragraphs = [cleanHtmlText(text) for text in paragraphPattern.findall(chunk)]
		if linkMatch is None or len(paragraphs) == 0 or paragraphs[0] == "":
			continue
		href = linkMatch.group(1)
		title = paragraphs[0]
		tags = [cleanHtmlText(text) for text in tagSpanPattern.findall(chunk)]
		location = tags[0] if len(tags) > 0 else ""
		experience = stripExperienceLabel(tags[1]) if len(tags) > 1 else ""
		description = paragraphs[1] if len(paragraphs) > 1 else ""
		jobs.append({
			"id": generateJobId(title, extractStableId(href)),
			"title": title,
			"link": href,
			"location": location,
			"department": "",
			"jobType": "",
			"experience": experience,
			"description": description,
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
		jobs = parseRolesHtml(html)
		if len(jobs) == 0:
			logger.error("devntech: roles section has no parsable role cards")
	except Exception as error:
		logger.exception("devntech: fetchState failed: %s", error)
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
		logger.exception("devntech: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("devntech: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("devntech: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("devntech: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())