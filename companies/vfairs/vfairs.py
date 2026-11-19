import datetime
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vfairs")

sourceUrl = "https://vfairs.zohorecruit.com/jobs/careers?"
snapshotPath = Path(__file__).parent / "vfairs.json"


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


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	errorOccurred = False
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=45000)
			await page.wait_for_selector("div.cw-filter-joblist", timeout=30000)
			await page.wait_for_timeout(2000)
			cardElements = await page.query_selector_all("div.cw-filter-joblist")
			cardIndex = 0
			cardCount = len(cardElements)
			while cardIndex < cardCount:
				card = cardElements[cardIndex]
				job = await parseCard(card)
				jobFound = job is not None
				if jobFound:
					jobs.append(job)
				cardIndex = cardIndex + 1
			await browser.close()
	except Exception as fetchException:
		errorOccurred = True
		logger.exception("Failed to fetch vfairs jobs: %s", fetchException)
	stateResult = "error" if errorOccurred else "open"
	state = dict(jobs=jobs, state=stateResult)
	return state


async def parseCard(card) -> dict[str, Any]:
	parsedJob = None
	try:
		linkElement = await card.query_selector("h3 a.cw-3-title")
		linkElementExists = linkElement is not None
		if not linkElementExists:
			return parsedJob
		rawTitle = await linkElement.inner_text()
		title = normalizeText(rawTitle)
		link = await linkElement.get_attribute("href")
		stableId = extractStableId(link)
		locationElement = await card.query_selector("p.filter-subhead")
		locationElementExists = locationElement is not None
		if locationElementExists:
			rawLocationBlock = await locationElement.inner_text()
			location = extractLocation(rawLocationBlock)
		else:
			location = ""
		jobTypeElement = await card.query_selector("span.cw-full-time")
		jobTypeElementExists = jobTypeElement is not None
		if jobTypeElementExists:
			rawJobType = await jobTypeElement.inner_text()
			jobType = normalizeText(rawJobType)
		else:
			jobType = ""
		postedAtElement = await card.query_selector("span.search-date-opened")
		postedAtElementExists = postedAtElement is not None
		if postedAtElementExists:
			rawPostedAt = await postedAtElement.inner_text()
			postedAt = normalizeText(rawPostedAt)
		else:
			postedAt = ""
		jobId = generateJobId(title, stableId)
		parsedJob = dict(
			id=jobId,
			title=title,
			link=link,
			location=location,
			department="",
			jobType=jobType,
			postedAt=postedAt,
			state="open",
		)
	except Exception as parseException:
		logger.exception("Failed to parse vfairs card: %s", parseException)
	return parsedJob


def extractLocation(rawLocationBlock: str) -> str:
	normalized = normalizeText(rawLocationBlock)
	splitParts = re.split(r"\s+\d", normalized)
	locationText = normalized
	hasSplit = len(splitParts) > 0
	if hasSplit:
		locationText = splitParts[0].strip()
	return locationText


def extractStableId(link: str) -> str:
	linkIsEmpty = link is None or link == ""
	if linkIsEmpty:
		return ""
	matchResult = re.search(r"/careers/(\d+)/", link)
	matchFound = matchResult is not None
	if matchFound:
		stableId = matchResult.group(1)
	else:
		stableId = ""
	return stableId


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
	logger.info("vfairs: wrote %d jobs", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())