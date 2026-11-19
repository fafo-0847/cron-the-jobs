import datetime
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("zaptatech")

sourceUrl = "https://career.zaptatech.com"
snapshotPath = Path(__file__).parent / "zaptatech.json"


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
			await page.wait_for_selector("div.main-jobs-container div.catogory", timeout=30000)
			await page.wait_for_timeout(2000)
			totalPages = await getTotalPages(page)
			currentPageNumber = 1
			while currentPageNumber <= totalPages:
				pageJobs = await scrapeCurrentPage(page)
				jobIndex = 0
				jobCount = len(pageJobs)
				while jobIndex < jobCount:
					jobs.append(pageJobs[jobIndex])
					jobIndex = jobIndex + 1
				isLastPage = currentPageNumber == totalPages
				if isLastPage:
					break
				nextPageNumber = currentPageNumber + 1
				await goToPage(page, nextPageNumber)
				currentPageNumber = nextPageNumber
			await browser.close()
	except Exception as fetchException:
		errorOccurred = True
		logger.exception("Failed to fetch zaptech jobs: %s", fetchException)
	stateResult = "error" if errorOccurred else "open"
	state = dict(jobs=jobs, state=stateResult)
	return state


async def getTotalPages(page) -> int:
	totalPages = 1
	try:
		pageLinkElements = await page.query_selector_all("ul.pagination li.page-item a.page-link")
		pageNumbers = []
		linkIndex = 0
		linkCount = len(pageLinkElements)
		while linkIndex < linkCount:
			linkElement = pageLinkElements[linkIndex]
			rawText = await linkElement.inner_text()
			cleanedText = rawText.strip()
			isNumeric = cleanedText.isdigit()
			if isNumeric:
				pageNumbers.append(int(cleanedText))
			linkIndex = linkIndex + 1
		hasPageNumbers = len(pageNumbers) > 0
		if hasPageNumbers:
			totalPages = max(pageNumbers)
	except Exception as paginationException:
		logger.exception("Failed to read total pages, defaulting to 1: %s", paginationException)
		totalPages = 1
	return totalPages


async def goToPage(page, pageNumber: int) -> None:
	pagedUrl = sourceUrl + "/?page=" + str(pageNumber)
	await page.goto(pagedUrl, wait_until="domcontentloaded", timeout=45000)
	await page.wait_for_selector("div.main-jobs-container div.catogory", timeout=30000)
	await page.wait_for_timeout(2000)


async def scrapeCurrentPage(page) -> list:
	pageJobs = []
	cardElements = await page.query_selector_all("div.main-jobs-container div.catogory")
	cardIndex = 0
	cardCount = len(cardElements)
	while cardIndex < cardCount:
		card = cardElements[cardIndex]
		job = await parseCard(card)
		jobFound = job is not None
		if jobFound:
			pageJobs.append(job)
		cardIndex = cardIndex + 1
	return pageJobs


async def parseCard(card) -> dict[str, Any]:
	parsedJob = None
	try:
		titleElement = await card.query_selector("h2.catogory-title")
		titleElementExists = titleElement is not None
		if not titleElementExists:
			return parsedJob
		rawTitle = await titleElement.inner_text()
		title = normalizeText(rawTitle)
		detailLinkElement = await card.query_selector("a.catogory-btn[href*='job-detail']")
		detailLinkElementExists = detailLinkElement is not None
		if detailLinkElementExists:
			link = await detailLinkElement.get_attribute("href")
		else:
			link = ""
		stableId = extractStableId(link)
		locationElement = await card.query_selector("p.data-detail")
		locationElementExists = locationElement is not None
		if locationElementExists:
			rawLocation = await locationElement.inner_text()
			location = normalizeText(rawLocation)
			locationHasLabel = ":" in location
			if locationHasLabel:
				location = ""
		else:
			location = ""
		department = await extractLabeledDetail(card, "Category:")
		postedAt = await extractLabeledDetail(card, "Posted:")
		stableIdIsEmpty = stableId == ""
		if stableIdIsEmpty:
			compositeKey = title + "|" + department + "|" + location
			stableId = compositeKey
		jobId = generateJobId(title, stableId)
		parsedJob = dict(
			id=jobId,
			title=title,
			link=link,
			location=location,
			department=department,
			jobType="",
			postedAt=postedAt,
			state="open",
		)
	except Exception as parseException:
		logger.exception("Failed to parse zaptech card: %s", parseException)
	return parsedJob


async def extractLabeledDetail(card, labelPrefix: str) -> str:
	detailValue = ""
	try:
		detailElements = await card.query_selector_all("p.data-detail")
		detailIndex = 0
		detailCount = len(detailElements)
		while detailIndex < detailCount:
			detailElement = detailElements[detailIndex]
			rawDetailText = await detailElement.inner_text()
			cleanedDetailText = normalizeText(rawDetailText)
			hasPrefix = cleanedDetailText.startswith(labelPrefix)
			if hasPrefix:
				detailValue = cleanedDetailText[len(labelPrefix):].strip()
				break
			detailIndex = detailIndex + 1
	except Exception as detailException:
		logger.exception("Failed to extract labeled detail %s: %s", labelPrefix, detailException)
	return detailValue


def extractStableId(link: str) -> str:
	linkIsEmpty = link is None or link == ""
	if linkIsEmpty:
		return ""
	matchResult = re.search(r"/job-detail/([A-Za-z0-9\-]+)", link)
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
	logger.info("zaptech: wrote %d jobs", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())