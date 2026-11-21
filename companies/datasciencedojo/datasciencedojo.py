import asyncio
import hashlib
import html
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

companyName = "datasciencedojo"
companyDir = Path(__file__).parent
snapshotPath = companyDir / f"{companyName}.json"

sourceUrl = "https://datasciencedojo.com/about/careers/"

siteUrl = "https://datasciencedojo.com"
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
# Site moved from Elementor (WordPress) to Astro in 2026. Each role is an <a class="role">
# card with role-category / role-title / role-meta spans; the page also carries a JSON-LD
# ItemList "#open-roles" which we use as a fallback and as a role count cross-check.
roleCardPattern = re.compile(r'<a href="(?P<href>[^"]*/jobs/[^"]+)" class="role"[^>]*>(?P<body>.*?)</a>', re.DOTALL)
roleSpanPattern = re.compile(r'<span class="role-(?P<kind>category|title|meta)"[^>]*>(?P<text>.*?)</span>', re.DOTALL)
jsonLdPattern = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def loadExistingSnapshot() -> dict[str, Any]:
	fileExists = snapshotPath.exists()
	if fileExists:
		try:
			rawText = snapshotPath.read_text()
			snapshot = json.loads(rawText)
			return snapshot
		except Exception as error:
			logger.warning("Failed to load existing snapshot for %s: %s", companyName, error)
			return {"jobs": []}
	else:
		return {"jobs": []}


def normalizeText(text: str) -> str:
	stripTagsPattern = re.compile(r'<[^>]+>')
	withoutTags = stripTagsPattern.sub("", text)
	unescaped = html.unescape(withoutTags)
	normalized = unescaped.replace("\xa0", " ").strip()
	return normalized


def extractSlugFromLink(link: str) -> str:
	trimmedLink = link.rstrip("/")
	segments = trimmedLink.split("/")
	hasSegments = len(segments) > 0
	if hasSegments:
		slug = segments[-1]
	else:
		slug = ""
	return slug


def buildJob(title: str, link: str, department: str = "", meta: str = "") -> dict:
	absoluteLink = link if link.startswith("http") else siteUrl + link
	metaParts = [part.strip() for part in meta.split("·")] if meta else []
	location = metaParts[0] if len(metaParts) > 0 else ""
	jobType = metaParts[1] if len(metaParts) > 1 else ""
	stableId = extractSlugFromLink(absoluteLink)
	job = {
		"id": generateJobId(title, stableId),
		"title": title,
		"link": absoluteLink,
		"location": location,
		"department": department,
		"jobType": jobType,
		"postedAt": "",
		"state": "open",
	}
	return job


def parseJsonLdRoles(htmlText: str) -> list | None:
	"""Returns the ItemList entries for #open-roles, or None when the list is absent."""
	for match in jsonLdPattern.finditer(htmlText):
		try:
			data = json.loads(match.group(1))
		except json.JSONDecodeError:
			continue
		graph = data.get("@graph", [data]) if isinstance(data, dict) else data
		for node in graph:
			isRolesList = isinstance(node, dict) and node.get("@type") == "ItemList" and "open-roles" in str(node.get("@id", ""))
			if isRolesList:
				return node.get("itemListElement", [])
	return None


def parseJobsFromHtml(htmlText: str) -> list:
	newJobs = []
	for cardMatch in roleCardPattern.finditer(htmlText):
		fields = {spanMatch.group("kind"): normalizeText(spanMatch.group("text")) for spanMatch in roleSpanPattern.finditer(cardMatch.group("body"))}
		title = fields.get("title", "")
		if title == "":
			continue
		newJobs.append(buildJob(title, cardMatch.group("href"), fields.get("category", ""), fields.get("meta", "")))
	if len(newJobs) == 0:
		for item in parseJsonLdRoles(htmlText) or []:
			title = normalizeText(str(item.get("name", "")))
			link = str(item.get("url", ""))
			if title != "" and link != "":
				newJobs.append(buildJob(title, link))
	return newJobs


async def fetchHtml(url: str) -> str:
	timeout = aiohttp.ClientTimeout(total=45)
	async with aiohttp.ClientSession(headers={"User-Agent": userAgent}, timeout=timeout) as session:
		async with session.get(url) as response:
			response.raise_for_status()
			return await response.text()


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	confirmedEmpty = False
	try:
		htmlText = await fetchHtml(url)
		jobs = parseJobsFromHtml(htmlText)
		jsonLdRoles = parseJsonLdRoles(htmlText)
		confirmedEmpty = len(jobs) == 0 and jsonLdRoles is not None and len(jsonLdRoles) == 0
		if len(jobs) == 0 and not confirmedEmpty:
			logger.error("%s: no role cards or JSON-LD roles found (layout changed)", companyName)
	except Exception as error:
		logger.exception("Failed to fetch %s: %s", companyName, error)
	state = {"jobs": jobs, "confirmedEmpty": confirmedEmpty}
	return state


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobs = state.get("jobs", [])
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("Suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
		return dict(existingSnapshot)
	snapshot = {
		"sourceUrl": sourceUrl,
		"fetchedAt": datetime.now(timezone.utc).isoformat(),
		"state": "open",
		"jobs": newJobs,
	}
	return snapshot


def writeSnapshot(snapshot: dict) -> None:
	try:
		snapshotText = json.dumps(snapshot, indent=2)
		snapshotPath.write_text(snapshotText)
	except Exception as error:
		logger.warning("Failed to write snapshot for %s: %s", companyName, error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	logging.basicConfig(level=logging.INFO)
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("Fetched %d jobs for %s", jobCount, companyName)


if __name__ == "__main__":
	asyncio.run(runMain())