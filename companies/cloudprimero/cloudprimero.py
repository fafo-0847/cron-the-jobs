import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cloudprimero")

sourceUrl = "https://careers.cloudprimero.com"
baseUrl = "https://careers.cloudprimero.com"
snapshotPath = Path(__file__).parent / "cloudprimero.json"


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
			await page.wait_for_selector("article.job-card", timeout=30000)
			await page.wait_for_timeout(2000)
			cardElements = await page.query_selector_all("article.job-card")
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
		logger.exception("Failed to fetch cloudprimero jobs: %s", fetchException)
	stateResult = "error" if errorOccurred else "open"
	state = dict(jobs=jobs, state=stateResult)
	return state


async def parseCard(card) -> dict[str, Any]:
	parsedJob = None
	try:
		linkElement = await card.query_selector("a.job-title-link")
		linkElementExists = linkElement is not None
		if not linkElementExists:
			return parsedJob
		stableId = await linkElement.get_attribute("data-job-id")
		hrefValue = await linkElement.get_attribute("href")
		link = buildAbsoluteLink(hrefValue)
		titleAttrValue = await linkElement.get_attribute("data-job-title")
		titleAttrExists = titleAttrValue is not None and titleAttrValue != ""
		if titleAttrExists:
			title = normalizeText(titleAttrValue)
		else:
			titleElement = await card.query_selector("h2.jobs-title")
			titleElementExists = titleElement is not None
			if titleElementExists:
				rawTitle = await titleElement.inner_text()
				title = normalizeText(rawTitle)
			else:
				title = ""
		cityAttrValue = await linkElement.get_attribute("data-job-city")
		countryAttrValue = await linkElement.get_attribute("data-job-country")
		location = buildLocation(cityAttrValue, countryAttrValue)
		jobId = generateJobId(title, stableId)
		parsedJob = dict(
			id=jobId,
			title=title,
			link=link,
			location=location,
			department="",
			jobType="",
			postedAt="",
			state="open",
		)
	except Exception as parseException:
		logger.exception("Failed to parse cloudprimero card: %s", parseException)
	return parsedJob


def buildLocation(cityValue: str, countryValue: str) -> str:
	cityIsEmpty = cityValue is None or cityValue == ""
	countryIsEmpty = countryValue is None or countryValue == ""
	if cityIsEmpty and countryIsEmpty:
		return ""
	if cityIsEmpty:
		return normalizeText(countryValue)
	if countryIsEmpty:
		return normalizeText(cityValue)
	location = cityValue + ", " + countryValue
	return normalizeText(location)


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
	logger.info("cloudprimero: wrote %d jobs", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())