import base64
import datetime
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright

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


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	errorOccurred = False
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=45000)
			await page.wait_for_selector("div[class*='categorySection']", timeout=30000)
			await page.wait_for_timeout(2000)
			categorySections = await page.query_selector_all("div[class*='categorySection']")
			categoryIndex = 0
			categoryCount = len(categorySections)
			while categoryIndex < categoryCount:
				categorySection = categorySections[categoryIndex]
				categoryJobs = await parseCategorySection(categorySection)
				jobIndex = 0
				jobCount = len(categoryJobs)
				while jobIndex < jobCount:
					jobs.append(categoryJobs[jobIndex])
					jobIndex = jobIndex + 1
				categoryIndex = categoryIndex + 1
			await browser.close()
	except Exception as fetchException:
		errorOccurred = True
		logger.exception("Failed to fetch ocloud jobs: %s", fetchException)
	stateResult = "error" if errorOccurred else "open"
	state = dict(jobs=jobs, state=stateResult)
	return state


async def parseCategorySection(categorySection) -> list:
	categoryJobs = []
	try:
		titleElement = await categorySection.query_selector("h2[class*='title']")
		titleElementExists = titleElement is not None
		if titleElementExists:
			rawCategoryName = await titleElement.inner_text()
			categoryName = normalizeText(rawCategoryName)
		else:
			categoryName = ""
		cardElements = await categorySection.query_selector_all("div[class*='root-']")
		cardIndex = 0
		cardCount = len(cardElements)
		while cardIndex < cardCount:
			card = cardElements[cardIndex]
			job = await parseCard(card, categoryName)
			jobFound = job is not None
			if jobFound:
				categoryJobs.append(job)
			cardIndex = cardIndex + 1
	except Exception as sectionException:
		logger.exception("Failed to parse ocloud category section: %s", sectionException)
	return categoryJobs


async def parseCard(card, categoryName: str) -> dict[str, Any]:
	parsedJob = None
	try:
		titleElement = await card.query_selector("h2[class*='title-']")
		titleElementExists = titleElement is not None
		if not titleElementExists:
			return parsedJob
		rawTitle = await titleElement.inner_text()
		title = normalizeText(rawTitle)
		linkElement = await card.query_selector("a[class*='button-']")
		linkElementExists = linkElement is not None
		if not linkElementExists:
			return parsedJob
		hrefValue = await linkElement.get_attribute("href")
		link = buildAbsoluteLink(hrefValue)
		stableId = extractStableId(hrefValue)
		pillElements = await card.query_selector_all("div[class*='pill-']")
		pillTexts = await extractPillTexts(pillElements)
		jobType = pillTexts[0] if len(pillTexts) > 0 else ""
		location = pillTexts[2] if len(pillTexts) > 2 else ""
		jobId = generateJobId(title, stableId)
		parsedJob = dict(
			id=jobId,
			title=title,
			link=link,
			location=location,
			department=categoryName,
			jobType=jobType,
			postedAt="",
			state="open",
		)
	except Exception as parseException:
		logger.exception("Failed to parse ocloud card: %s", parseException)
	return parsedJob


async def extractPillTexts(pillElements) -> list:
	pillTexts = []
	pillIndex = 0
	pillCount = len(pillElements)
	while pillIndex < pillCount:
		pillElement = pillElements[pillIndex]
		rawPillText = await pillElement.inner_text()
		pillTexts.append(normalizeText(rawPillText))
		pillIndex = pillIndex + 1
	return pillTexts


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