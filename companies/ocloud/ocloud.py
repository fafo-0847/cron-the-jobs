import base64
import datetime
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ocloud")

sourceUrl = "https://ocloudsolutions.net/careers/"
baseUrl = "https://ocloudsolutions.net"
snapshotPath = Path(__file__).parent / "ocloud.json"


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


# The Gatsby careers page now renders "404" after hydration in a browser, so the old
# DOM scrape never finds a card. The job posts come from a Gatsby static query; read
# that JSON directly. Job posts are WordPress posts in category "job"; their excerpt
# carries "key=value" lines (jobType, experience, location, googleFormLink).
staticQueryUrl = "https://ocloudsolutions.net/page-data/sq/d/2367572342.json"
careersPageDataUrl = "https://ocloudsolutions.net/page-data/careers/page-data.json"
staticQueryHashPattern = re.compile(r'"staticQueryHashes"\s*:\s*\[([^\]]*)\]')
excerptFieldPattern = re.compile(r"(\w+)=([^<\n]+)")


def parseExcerptFields(excerpt: str) -> dict[str, str]:
	fields: dict[str, str] = {}
	for key, value in excerptFieldPattern.findall(excerpt or ""):
		fields[key] = normalizeText(value)
	return fields


def parsePosts(posts: list[dict]) -> list[dict[str, Any]]:
	jobs: list[dict[str, Any]] = []
	for post in posts:
		categoryNames = [(node.get("name") or "") for node in (post.get("categories") or {}).get("nodes", [])]
		isJobPost = "job" in categoryNames
		if not isJobPost:
			continue
		title = normalizeText(post.get("title") or "")
		relayId = str(post.get("id") or "")
		if title == "" or relayId == "":
			continue
		fields = parseExcerptFields(post.get("excerpt") or "")
		department = next((name for name in categoryNames if name != "job" and not name.startswith("blog")), "")
		href = f"/job/{relayId}/"
		jobs.append(dict(
			id=generateJobId(title, extractStableId(href)),
			title=title,
			link=buildAbsoluteLink(href),
			location=fields.get("location", ""),
			department=department,
			jobType=fields.get("jobType", ""),
			postedAt=post.get("date") or "",
			state="open",
		))
	return jobs


async def getJson(session: aiohttp.ClientSession, url: str) -> Any:
	async with session.get(url) as response:
		response.raise_for_status()
		return await response.json(content_type=None)


async def fetchPostsData(session: aiohttp.ClientSession) -> dict:
	# Prefer the hash the careers page currently lists, since Gatsby re-hashes on rebuilds.
	candidateUrls = []
	try:
		pageData = await getJson(session, careersPageDataUrl)
		for queryHash in pageData.get("staticQueryHashes", []):
			candidateUrls.append(f"{baseUrl}/page-data/sq/d/{queryHash}.json")
	except Exception as error:
		logger.warning("ocloud: could not read careers page-data, using known static query: %s", error)
	if staticQueryUrl not in candidateUrls:
		candidateUrls.append(staticQueryUrl)
	for candidateUrl in candidateUrls:
		data = (await getJson(session, candidateUrl)).get("data", {})
		ocloudsData = data.get("ocloudsData") or {}
		posts = (ocloudsData.get("posts") or {}).get("nodes")
		if isinstance(posts, list):
			return {"posts": posts}
	raise ValueError("ocloud: no static query with ocloudsData.posts found")


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	errorOccurred = False
	confirmedEmpty = False
	try:
		timeout = aiohttp.ClientTimeout(total=45)
		async with aiohttp.ClientSession(timeout=timeout) as session:
			postsData = await fetchPostsData(session)
		jobs = parsePosts(postsData["posts"])
		confirmedEmpty = len(jobs) == 0
	except Exception as fetchException:
		errorOccurred = True
		logger.exception("Failed to fetch ocloud jobs: %s", fetchException)
	stateResult = "error" if errorOccurred else "open"
	state = dict(jobs=jobs, state=stateResult, confirmedEmpty=confirmedEmpty)
	return state


def extractStableId(hrefValue: str) -> str:
	hrefIsEmpty = hrefValue is None or hrefValue == ""
	if hrefIsEmpty:
		return ""
	matchResult = re.search(r"/job/([A-Za-z0-9+/=]+?)/?$", hrefValue)
	matchFound = matchResult is not None
	if not matchFound:
		return ""
	encodedSlug = matchResult.group(1)
	stableId = decodeRelayId(encodedSlug)
	return stableId


def decodeRelayId(encodedSlug: str) -> str:
	stableId = ""
	try:
		paddingNeeded = (4 - len(encodedSlug) % 4) % 4
		paddedSlug = encodedSlug + ("=" * paddingNeeded)
		decodedBytes = base64.b64decode(paddedSlug)
		decodedText = decodedBytes.decode("utf-8")
		decodedMatch = re.search(r"(\d+)$", decodedText)
		decodedMatchFound = decodedMatch is not None
		if decodedMatchFound:
			stableId = decodedMatch.group(1)
		else:
			stableId = encodedSlug
	except Exception as decodeException:
		logger.warning("Failed to decode relay id %s, falling back to raw slug: %s", encodedSlug, decodeException)
		stableId = encodedSlug
	return stableId


def buildAbsoluteLink(hrefValue: str) -> str:
	hrefIsEmpty = hrefValue is None or hrefValue == ""
	if hrefIsEmpty:
		return ""
	hrefIsAbsolute = hrefValue.startswith("http")
	if hrefIsAbsolute:
		absoluteLink = hrefValue
	else:
		absoluteLink = baseUrl + hrefValue
	return absoluteLink


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
	logger.info("ocloud: wrote %d jobs", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())