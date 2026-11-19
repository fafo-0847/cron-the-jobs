import datetime
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("siemens")

sourceUrl = "https://jobs.siemens.com/en_US/externaljobs/SearchJobs/?42414=%5B812046%5D&42414_format=17570&listFilterMode=1&folderRecordsPerPage=6&"
snapshotPath = Path(__file__).parent / "siemens.json"


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
			await page.wait_for_selector("article.article--result", timeout=30000)
			await page.wait_for_timeout(2000)
			cardElements = await page.query_selector_all("article.article--result")
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
		logger.exception("Failed to fetch siemens jobs: %s", fetchException)
	stateResult = "error" if errorOccurred else "open"
	state = dict(jobs=jobs, state=stateResult)
	return state


async def parseCard(card) -> dict[str, Any]:
	parsedJob = None
	try:
		titleLinkElement = await card.query_selector("h3.article__header__text__title a")
		titleLinkExists = titleLinkElement is not None
		if not titleLinkExists:
			return parsedJob
		rawTitleText = await titleLinkElement.inner_text()
		title = normalizeText(rawTitleText)
		link = await titleLinkElement.get_attribute("href")
		stableId = extractStableId(link)
		locationElement = await card.query_selector("span.list-item-location")
		locationExists = locationElement is not None
		if locationExists:
			rawLocation = await locationElement.inner_text()
			location = normalizeText(rawLocation)
		else:
			location = ""
		departmentElement = await card.query_selector("span.list-item-family")
		departmentExists = departmentElement is not None
		if departmentExists:
			rawDepartment = await departmentElement.inner_text()
			department = normalizeText(rawDepartment)
		else:
			department = ""
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
		logger.exception("Failed to parse siemens card: %s", parseException)
	return parsedJob


def extractStableId(link: str) -> str:
	linkIsEmpty = link is None or link == ""
	if linkIsEmpty:
		return ""
	matchResult = re.search(r"/JobDetail/(\d+)", link)
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
	logger.info("siemens: wrote %d jobs", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())