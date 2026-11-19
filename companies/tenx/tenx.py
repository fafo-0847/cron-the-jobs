import datetime
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tenx")

sourceUrl = "https://tenx.webhr.co/hr/careers/"
snapshotPath = Path(__file__).parent / "tenx.json"


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
			await page.wait_for_selector("div.ant-card-meta-title", timeout=30000)
			await page.wait_for_timeout(2000)
			cardElements = await page.query_selector_all("div.ant-card")
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
		logger.exception("Failed to fetch tenx jobs: %s", fetchException)
	stateResult = "error" if errorOccurred else "open"
	state = dict(jobs=jobs, state=stateResult)
	return state


async def parseCard(card) -> dict[str, Any]:
	parsedJob = None
	try:
		titleElement = await card.query_selector("div.ant-card-meta-title")
		titleElementExists = titleElement is not None
		if not titleElementExists:
			return parsedJob
		rawTitle = await titleElement.inner_text()
		fullTitle = normalizeText(rawTitle)
		fullTitleIsEmpty = fullTitle == ""
		if fullTitleIsEmpty:
			return parsedJob
		title = stripStableIdSuffix(fullTitle)
		stableId = extractStableId(fullTitle)
		departmentElement = await card.query_selector("div.ant-card-meta-description")
		departmentElementExists = departmentElement is not None
		if departmentElementExists:
			rawDepartment = await departmentElement.inner_text()
			department = normalizeText(rawDepartment)
		else:
			department = ""
		valueElements = await card.query_selector_all("span.ant-typography.value-0-2-14")
		valueTexts = await extractValueTexts(valueElements)
		jobType = valueTexts[0] if len(valueTexts) > 0 else ""
		officeLocation = valueTexts[1] if len(valueTexts) > 1 else ""
		cityElement = await card.query_selector("span.ant-typography[style*='margin-right']")
		cityElementExists = cityElement is not None
		if cityElementExists:
			rawCity = await cityElement.inner_text()
			city = normalizeText(rawCity).rstrip(",")
		else:
			city = ""
		location = buildLocation(city, officeLocation)
		jobId = generateJobId(title, stableId)
		parsedJob = dict(
			id=jobId,
			title=title,
			link="",
			location=location,
			department=department,
			jobType=jobType,
			postedAt="",
			state="open",
		)
	except Exception as parseException:
		logger.exception("Failed to parse tenx card: %s", parseException)
	return parsedJob


async def extractValueTexts(valueElements) -> list:
	valueTexts = []
	valueIndex = 0
	valueCount = len(valueElements)
	while valueIndex < valueCount:
		valueElement = valueElements[valueIndex]
		rawValueText = await valueElement.inner_text()
		valueTexts.append(normalizeText(rawValueText))
		valueIndex = valueIndex + 1
	return valueTexts


def buildLocation(city: str, officeLocation: str) -> str:
	cityIsEmpty = city == ""
	officeIsEmpty = officeLocation == ""
	if cityIsEmpty and officeIsEmpty:
		return ""
	if cityIsEmpty:
		return officeLocation
	if officeIsEmpty:
		return city
	combined = city + ", " + officeLocation
	return combined


def extractStableId(fullTitle: str) -> str:
	matchResult = re.search(r"-\s*(\d+)\s*$", fullTitle)
	matchFound = matchResult is not None
	if matchFound:
		stableId = matchResult.group(1)
	else:
		stableId = ""
	return stableId


def stripStableIdSuffix(fullTitle: str) -> str:
	strippedTitle = re.sub(r"\s*-\s*\d+\s*$", "", fullTitle)
	return strippedTitle.strip()


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
	logger.info("tenx: wrote %d jobs", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())