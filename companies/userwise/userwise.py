import datetime
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("userwise")

sourceUrl = "https://userwise.io/career/"
snapshotPath = Path(__file__).parent / "userwise.json"


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
			await page.wait_for_selector("div.career-item", timeout=30000)
			await page.wait_for_timeout(2000)
			cardElements = await page.query_selector_all("div.career-item")
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
		logger.exception("Failed to fetch userwise jobs: %s", fetchException)
	stateResult = "error" if errorOccurred else "open"
	state = dict(jobs=jobs, state=stateResult)
	return state


async def parseCard(card) -> dict[str, Any]:
	parsedJob = None
	try:
		titleElement = await card.query_selector("h3.career-title")
		titleElementExists = titleElement is not None
		if not titleElementExists:
			return parsedJob
		rawTitle = await titleElement.inner_text()
		title = normalizeText(rawTitle)
		titleIsEmpty = title == ""
		if titleIsEmpty:
			return parsedJob
		linkElement = await card.query_selector("a.career-link")
		linkElementExists = linkElement is not None
		if not linkElementExists:
			linkElement = await card.query_selector("div.career-content-lst a")
			linkElementExists = linkElement is not None
		if linkElementExists:
			link = await linkElement.get_attribute("href")
		else:
			link = ""
		stableId = extractStableId(link)
		department = await card.get_attribute("data-department")
		department = department if department is not None else ""
		workplaceType = await card.get_attribute("data-workplace")
		workplaceType = workplaceType if workplaceType is not None else ""
		metaElement = await card.query_selector("p.career-meta")
		metaElementExists = metaElement is not None
		if metaElementExists:
			rawMeta = await metaElement.inner_text()
			location = extractLocation(rawMeta)
		else:
			location = ""
		jobId = generateJobId(title, stableId)
		parsedJob = dict(
			id=jobId,
			title=title,
			link=link,
			location=location,
			department=department,
			jobType=workplaceType,
			postedAt="",
			state="open",
		)
	except Exception as parseException:
		logger.exception("Failed to parse userwise card: %s", parseException)
	return parsedJob


def extractLocation(rawMeta: str) -> str:
	normalized = normalizeText(rawMeta)
	pipeParts = normalized.split("|")
	locationText = ""
	hasSecondPart = len(pipeParts) > 1
	if hasSecondPart:
		locationText = pipeParts[1].strip()
	return locationText


def extractStableId(link: str) -> str:
	linkIsEmpty = link is None or link == ""
	if linkIsEmpty:
		return ""
	matchResult = re.search(r"/jobs/(\d+)", link)
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
	logger.info("userwise: wrote %d jobs", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())