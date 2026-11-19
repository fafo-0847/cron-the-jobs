import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("securiti")

sourceUrl = 'https://careers.veeam.com/search-jobs?acm=ALL&alrpm=ALL&ascf=[%7B"key":"Team","value":"Securiti+AI"%7D]'
baseUrl = "https://careers.veeam.com"
snapshotPath = Path(__file__).parent / "securiti.json"


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
			await page.wait_for_selector("ul.job-list li", timeout=30000)
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
				await goToPage(page, url, nextPageNumber)
				currentPageNumber = nextPageNumber
			await browser.close()
	except Exception as fetchException:
		errorOccurred = True
		logger.exception("Failed to fetch securiti jobs: %s", fetchException)
	stateResult = "error" if errorOccurred else "open"
	state = dict(jobs=jobs, state=stateResult)
	return state


async def getTotalPages(page) -> int:
	totalPages = 1
	try:
		totalPagesElement = await page.query_selector("span.pagination-total-pages")
		totalPagesElementExists = totalPagesElement is not None
		if totalPagesElementExists:
			rawText = await totalPagesElement.inner_text()
			cleanedText = rawText.replace("/", "").strip()
			totalPages = int(cleanedText)
	except Exception as paginationException:
		logger.exception("Failed to read total pages, defaulting to 1: %s", paginationException)
		totalPages = 1
	return totalPages


async def goToPage(page, url: str, pageNumber: int) -> None:
	separator = "&" if "?" in url else "?"
	pagedUrl = url + separator + "p=" + str(pageNumber)
	await page.goto(pagedUrl, wait_until="domcontentloaded", timeout=45000)
	await page.wait_for_selector("ul.job-list li", timeout=30000)
	await page.wait_for_timeout(2000)


async def scrapeCurrentPage(page) -> list:
	pageJobs = []
	cardElements = await page.query_selector_all("ul.job-list li")
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
		linkElement = await card.query_selector("a[data-job-id]")
		linkElementExists = linkElement is not None
		if not linkElementExists:
			return parsedJob
		stableId = await linkElement.get_attribute("data-job-id")
		hrefValue = await linkElement.get_attribute("href")
		link = buildAbsoluteLink(hrefValue)
		titleElement = await card.query_selector("h2.job-list__title")
		titleElementExists = titleElement is not None
		if titleElementExists:
			rawTitle = await titleElement.inner_text()
			title = normalizeText(rawTitle)
		else:
			title = ""
		categoryElement = await card.query_selector("span.job-list__category")
		categoryElementExists = categoryElement is not None
		if categoryElementExists:
			rawCategory = await categoryElement.inner_text()
			department = normalizeText(rawCategory)
		else:
			department = ""
		locationElement = await card.query_selector("span.job-list__location")
		locationElementExists = locationElement is not None
		if locationElementExists:
			rawLocation = await locationElement.inner_text()
			location = normalizeText(rawLocation)
		else:
			location = ""
		jobId = generateJobId(title, stableId)
		parsedJob = dict(
			id=jobId,
			title=title,
			link=link,
			location=location,
			department=department,
			jobType="",
			postedAt="",
			state="open",
		)
	except Exception as parseException:
		logger.exception("Failed to parse securiti card: %s", parseException)
	return parsedJob


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
	logger.info("securiti: wrote %d jobs", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())