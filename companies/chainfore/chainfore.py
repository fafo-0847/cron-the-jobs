import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chainfore")

sourceUrl = "https://chainfore.com/careers/"
snapshotPath = Path(__file__).parent / "chainfore.json"


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
			await page.wait_for_selector("div.grid.gap-6 > div", timeout=30000)
			await page.wait_for_timeout(2000)
			cardElements = await page.query_selector_all("div.grid.gap-6 > div")
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
		logger.exception("Failed to fetch chainfore jobs: %s", fetchException)
	stateResult = "error" if errorOccurred else "open"
	state = dict(jobs=jobs, state=stateResult)
	return state


async def parseCard(card) -> dict[str, Any]:
	parsedJob = None
	try:
		titleElement = await card.query_selector("h3")
		titleElementExists = titleElement is not None
		if not titleElementExists:
			return parsedJob
		rawTitle = await titleElement.inner_text()
		title = normalizeText(rawTitle)
		metaElement = await card.query_selector("h3 + div")
		metaElementExists = metaElement is not None
		if metaElementExists:
			metaSpans = await metaElement.query_selector_all("span")
			metaTexts = await extractSpanTexts(metaSpans)
		else:
			metaTexts = []
		department = metaTexts[0] if len(metaTexts) > 0 else ""
		location = metaTexts[1] if len(metaTexts) > 1 else ""
		jobType = metaTexts[2] if len(metaTexts) > 2 else ""
		compositeKey = title + "|" + department + "|" + location + "|" + jobType
		jobId = generateJobId(title, compositeKey)
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
		logger.exception("Failed to parse chainfore card: %s", parseException)
	return parsedJob


async def extractSpanTexts(spanElements) -> list:
	spanTexts = []
	spanIndex = 0
	spanCount = len(spanElements)
	while spanIndex < spanCount:
		spanElement = spanElements[spanIndex]
		rawSpanText = await spanElement.inner_text()
		spanTexts.append(normalizeText(rawSpanText))
		spanIndex = spanIndex + 1
	return spanTexts


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
	logger.info("chainfore: wrote %d jobs", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())