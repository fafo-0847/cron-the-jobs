import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tekvaly")

sourceUrl = "https://hiredroid.com/jobs/tekvaly.com"
snapshotPath = Path(__file__).parent / "tekvaly.json"


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
			await page.wait_for_selector("div.MuiGrid2-container", timeout=30000)
			await page.wait_for_timeout(2000)
			keepPaging = True
			while keepPaging:
				pageJobs = await scrapeCurrentPage(page)
				jobIndex = 0
				jobCount = len(pageJobs)
				while jobIndex < jobCount:
					jobs.append(pageJobs[jobIndex])
					jobIndex = jobIndex + 1
				keepPaging = await goToNextPageIfAvailable(page)
			await browser.close()
	except Exception as fetchException:
		errorOccurred = True
		logger.exception("Failed to fetch tekvaly jobs: %s", fetchException)
	stateResult = "error" if errorOccurred else "open"
	state = dict(jobs=jobs, state=stateResult)
	return state


async def scrapeCurrentPage(page) -> list:
	pageJobs = []
	cardElements = await page.query_selector_all("span[aria-label='Job posted for']")
	cardIndex = 0
	cardCount = len(cardElements)
	while cardIndex < cardCount:
		posterSpan = cardElements[cardIndex]
		card = await posterSpan.evaluate_handle(
			"el => el.closest('.MuiGrid2-container')"
		)
		cardIsValid = card is not None
		if cardIsValid:
			job = await parseCard(card)
			jobFound = job is not None
			if jobFound:
				pageJobs.append(job)
		cardIndex = cardIndex + 1
	return pageJobs


async def parseCard(card) -> dict[str, Any]:
	parsedJob = None
	try:
		titleElement = await card.query_selector("span[aria-label='Recruiter'], a > span")
		titleElementExists = titleElement is not None
		if titleElementExists:
			rawTitle = await titleElement.inner_text()
			title = normalizeText(rawTitle)
		else:
			title = ""
		titleIsEmpty = title == ""
		if titleIsEmpty:
			return parsedJob
		locationElement = await card.query_selector("p span[aria-label='Location']")
		locationElementExists = locationElement is not None
		if not locationElementExists:
			locationElement = await card.query_selector("p.MuiTypography-body1 span.css-ek70zq")
		if locationElementExists:
			rawLocation = await locationElement.inner_text()
			location = normalizeText(rawLocation)
		else:
			location = ""
		workplaceTypeElement = await card.query_selector("span[alt='Timing'] + span.css-ek70zq")
		workplaceTypeElementExists = workplaceTypeElement is not None
		if not workplaceTypeElementExists:
			workplaceTypeElement = await card.query_selector("span[alt='Timing']")
		if workplaceTypeElementExists:
			rawWorkplaceType = await workplaceTypeElement.inner_text()
			jobType = normalizeText(rawWorkplaceType)
		else:
			jobType = ""
		compositeKey = title + "|" + location + "|" + jobType
		jobId = generateJobId(title, compositeKey)
		parsedJob = dict(
			id=jobId,
			title=title,
			link="",
			location=location,
			department="",
			jobType=jobType,
			postedAt="",
			state="open",
		)
	except Exception as parseException:
		logger.exception("Failed to parse tekvaly card: %s", parseException)
	return parsedJob


async def goToNextPageIfAvailable(page) -> bool:
	nextPageAvailable = False
	try:
		nextButton = await page.query_selector("button[aria-label='Go to next page']")
		nextButtonExists = nextButton is not None
		if not nextButtonExists:
			return nextPageAvailable
		isDisabled = await nextButton.is_disabled()
		if isDisabled:
			return nextPageAvailable
		await nextButton.click()
		await page.wait_for_timeout(2000)
		nextPageAvailable = True
	except Exception as paginationException:
		logger.exception("Failed to navigate to next page: %s", paginationException)
		nextPageAvailable = False
	return nextPageAvailable


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
	logger.info("tekvaly: wrote %d jobs", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())