import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("alethia")

sourceUrl = "https://www.alethia.ai/careers"
snapshotPath = Path(__file__).parent / "alethia.json"


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
		logger.exception("Failed to fetch alethia jobs: %s", fetchException)
	stateResult = "error" if errorOccurred else "open"
	state = dict(jobs=jobs, state=stateResult)
	return state


async def parseCard(card) -> dict[str, Any]:
	parsedJob = None
	try:
		titleElement = await card.query_selector("span.job-card__title")
		titleElementExists = titleElement is not None
		if not titleElementExists:
			return parsedJob
		rawTitle = await titleElement.inner_text()
		title = normalizeText(rawTitle)
		titleIsEmpty = title == ""
		if titleIsEmpty:
			return parsedJob
		tagElement = await card.query_selector("span.job-card__tag")
		tagElementExists = tagElement is not None
		if tagElementExists:
			rawTag = await tagElement.inner_text()
			department = normalizeText(rawTag)
		else:
			department = ""
		metaElements = await card.query_selector_all("span.job-card__meta")
		metaTexts = await extractMetaTexts(metaElements)
		workplaceType = metaTexts[0] if len(metaTexts) > 0 else ""
		jobType = metaTexts[1] if len(metaTexts) > 1 else ""
		combinedJobType = buildCombinedJobType(workplaceType, jobType)
		compositeKey = title + "|" + department + "|" + combinedJobType
		jobId = generateJobId(title, compositeKey)
		parsedJob = dict(
			id=jobId,
			title=title,
			link="",
			location=workplaceType,
			department=department,
			jobType=jobType,
			postedAt="",
			state="open",
		)
	except Exception as parseException:
		logger.exception("Failed to parse alethia card: %s", parseException)
	return parsedJob


def buildCombinedJobType(workplaceType: str, jobType: str) -> str:
	workplaceIsEmpty = workplaceType == ""
	jobTypeIsEmpty = jobType == ""
	if workplaceIsEmpty and jobTypeIsEmpty:
		return ""
	if workplaceIsEmpty:
		return jobType
	if jobTypeIsEmpty:
		return workplaceType
	combined = workplaceType + " " + jobType
	return combined


async def extractMetaTexts(metaElements) -> list:
	metaTexts = []
	metaIndex = 0
	metaCount = len(metaElements)
	while metaIndex < metaCount:
		metaElement = metaElements[metaIndex]
		rawMetaText = await metaElement.inner_text()
		metaTexts.append(normalizeText(rawMetaText))
		metaIndex = metaIndex + 1
	return metaTexts


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
	logger.info("alethia: wrote %d jobs", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())