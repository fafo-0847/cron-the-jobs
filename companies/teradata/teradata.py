import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright

from companies._shared import emptyboard

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("teradata")

sourceUrl = "https://careers.teradata.com/jobs?location=Pakistan"
noJobsPattern = re.compile(r"No Jobs Matching Criteria", re.I)
snapshotPath = Path(__file__).parent / "teradata.json"


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
	confirmedEmpty = False
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=45000)
			# gr8people search pages say "Search Returned No Jobs Matching Criteria" when the
			# Pakistan filter has nothing (seen Nov 2026), instead of rendering result cards.
			confirmedEmpty = await emptyboard.waitForJobsOrEmptyNotice(page, "article[data-cy='job-search-result-card']", noJobsPattern, 30000)
			await page.wait_for_timeout(2000)
			cardElements = await page.query_selector_all("article[data-cy='job-search-result-card']")
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
		logger.exception("Failed to fetch teradata jobs: %s", fetchException)
	stateResult = "error" if errorOccurred else "open"
	state = dict(jobs=jobs, state=stateResult, confirmedEmpty=confirmedEmpty and not errorOccurred)
	return state


async def parseCard(card) -> dict[str, Any]:
	parsedJob = None
	try:
		titleLinkElement = await card.query_selector("h4[data-cy='job-title'] a")
		titleLinkExists = titleLinkElement is not None
		if not titleLinkExists:
			return parsedJob
		rawTitleText = await titleLinkElement.inner_text()
		hrefValue = await titleLinkElement.get_attribute("href")
		stableId = extractStableId(hrefValue)
		title = cleanTitle(rawTitleText, stableId)
		locationElement = await card.query_selector("p[data-cy='job-location']")
		locationExists = locationElement is not None
		if locationExists:
			location = await locationElement.inner_text()
		else:
			location = ""
		jobType = await extractJobType(card)
		link = buildAbsoluteLink(hrefValue)
		jobId = generateJobId(title, stableId)
		parsedJob = dict(
			id=jobId,
			title=title,
			link=link,
			location=normalizeLocation(location),
			department="",
			jobType=jobType,
			postedAt="",
			state="open",
		)
	except Exception as parseException:
		logger.exception("Failed to parse teradata card: %s", parseException)
	return parsedJob


def extractStableId(hrefValue: str) -> str:
	hrefIsEmpty = hrefValue is None or hrefValue == ""
	if hrefIsEmpty:
		return ""
	matchResult = re.search(r"/jobs/(\d+)/", hrefValue)
	matchFound = matchResult is not None
	if matchFound:
		stableId = matchResult.group(1)
	else:
		stableId = ""
	return stableId


def cleanTitle(rawTitleText: str, stableId: str) -> str:
	suffix = " - " + stableId
	titleHasSuffix = rawTitleText.endswith(suffix)
	if titleHasSuffix:
		cleanedTitle = rawTitleText[: -len(suffix)]
	else:
		cleanedTitle = rawTitleText
	strippedTitle = cleanedTitle.strip()
	return strippedTitle


def buildAbsoluteLink(hrefValue: str) -> str:
	hrefIsEmpty = hrefValue is None or hrefValue == ""
	if hrefIsEmpty:
		return ""
	hrefIsAbsolute = hrefValue.startswith("http")
	if hrefIsAbsolute:
		absoluteLink = hrefValue
	else:
		absoluteLink = "https://careers.teradata.com" + hrefValue
	return absoluteLink


async def extractJobType(card) -> str:
	chipElements = await card.query_selector_all("div[role='list'][aria-label='Attributes'] div[role='listitem']")
	chipTexts = []
	chipIndex = 0
	chipCount = len(chipElements)
	while chipIndex < chipCount:
		chipElement = chipElements[chipIndex]
		chipText = await chipElement.inner_text()
		chipTexts.append(chipText.strip())
		chipIndex = chipIndex + 1
	jobType = ", ".join(chipTexts)
	return jobType


def normalizeLocation(text: str) -> str:
	normalized = text.replace("\xa0", " ").strip()
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
	import datetime
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
	logger.info("teradata: wrote %d jobs", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())