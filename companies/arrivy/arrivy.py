import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

companyName = "arrivy"
companyDir = Path(__file__).parent
snapshotPath = companyDir / f"{companyName}.json"

sourceUrl = "https://www.arrivy.com/careers/"

categoryMarker = 'class="job-category-section'
categoryTitlePattern = re.compile(r'class="[^"]*category-title[^"]*">\s*(.*?)\s*</h3>', re.DOTALL)
jobCardMarker = 'class="job-card '
jobTitlePattern = re.compile(r'class="[^"]*job-title-text[^"]*">\s*(.*?)\s*</div>', re.DOTALL)
applyLinkPattern = re.compile(r'<a href="([^"]+)"')
spanPattern = re.compile(r'<span[^>]*>([^<]*)</span>')


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
	normalized = text.replace("\xa0", " ").strip()
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


def parseJobChunk(chunk: str, category: str) -> dict[str, Any]:
	titleMatch = jobTitlePattern.search(chunk)
	rawTitle = ""
	if titleMatch is not None:
		rawTitle = titleMatch.group(1)
	applyMatch = applyLinkPattern.search(chunk)
	link = ""
	if applyMatch is not None:
		link = applyMatch.group(1)
	spanMatches = spanPattern.findall(chunk)
	cleanedSpans = []
	spanIndex = 0
	while spanIndex < len(spanMatches):
		spanText = normalizeText(spanMatches[spanIndex])
		isBulletOrEmpty = spanText in ("", "•")
		if not isBulletOrEmpty:
			cleanedSpans.append(spanText)
		spanIndex = spanIndex + 1
	rawLocation = ""
	rawJobType = ""
	hasLocation = len(cleanedSpans) > 0
	if hasLocation:
		rawLocation = cleanedSpans[0]
	hasJobType = len(cleanedSpans) > 1
	if hasJobType:
		rawJobType = cleanedSpans[1]
	job = {
		"title": rawTitle,
		"link": link,
		"location": rawLocation,
		"jobType": rawJobType,
		"department": category,
	}
	return job


def parseJobsFromHtml(htmlText: str) -> list:
	categoryChunks = htmlText.split(categoryMarker)
	parsedJobs = []
	categoryIndex = 1
	while categoryIndex < len(categoryChunks):
		categoryChunk = categoryChunks[categoryIndex]
		categoryTitleMatch = categoryTitlePattern.search(categoryChunk)
		rawCategory = ""
		if categoryTitleMatch is not None:
			rawCategory = categoryTitleMatch.group(1)
		category = normalizeText(rawCategory)
		jobChunks = categoryChunk.split(jobCardMarker)
		jobIndex = 1
		while jobIndex < len(jobChunks):
			jobChunk = jobChunks[jobIndex]
			parsedJob = parseJobChunk(jobChunk, category)
			title = normalizeText(parsedJob.get("title", ""))
			link = parsedJob.get("link", "")
			hasTitleAndLink = title != "" and link != ""
			if hasTitleAndLink:
				stableId = extractSlugFromLink(link)
				jobId = generateJobId(title, stableId)
				job = {
					"id": jobId,
					"title": title,
					"link": link,
					"location": normalizeText(parsedJob.get("location", "")),
					"department": category,
					"jobType": normalizeText(parsedJob.get("jobType", "")),
					"postedAt": "",
					"state": "open",
				}
				parsedJobs.append(job)
			jobIndex = jobIndex + 1
		categoryIndex = categoryIndex + 1
	return parsedJobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	htmlText = ""
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page(
				user_agent=(
					"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
					"(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
				)
			)
			await page.goto(url, wait_until="networkidle", timeout=45000)
			await page.wait_for_selector(".job-card", timeout=20000)
			await page.wait_for_timeout(1500)
			htmlText = await page.content()
			await browser.close()
	except Exception as error:
		logger.warning("Failed to fetch %s: %s", companyName, error)
	jobs = parseJobsFromHtml(htmlText)
	state = {"jobs": jobs}
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