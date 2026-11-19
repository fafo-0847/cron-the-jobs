import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

companyName = "invozone"
companyDir = Path(__file__).parent
snapshotPath = companyDir / f"{companyName}.json"

sourceUrl = "https://next.invozone.com/jobs"

cardMarker = '<div id="'
titlePattern = re.compile(r'title="([^"]+)"')
jobTypePattern = re.compile(r'•\s*(.*?)\s*</div>')
locationPattern = re.compile(
	r'<div class="mt-3 flex align-items-center">\s*<svg class="icon ml-0 mr-1" xmlns.*?</svg>\s*(.*?)\s*</div>',
	re.DOTALL,
)
departmentPattern = re.compile(
	r'<div class="mt-3 flex align-items-center">\s*<svg class="icon ml-0 mr-1" style="--icon-stroke.*?</svg>\s*(.*?)\s*</div>',
	re.DOTALL,
)
closingDatePattern = re.compile(r'Closes on:\s*<b>(.*?)</b>')
postedAtPattern = re.compile(r'·\s*(.*?)\s*</span>')


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def loadExistingSnapshot() -> dict[str, Any]:
	fileExists = snapshotPath.exists()
	if fileExists:
		try:
			rawText = snapshotPath.read_text()
			snapshot = json.loads(rawText)
			return snapshot
		except Exception as error:
			logger.warning("Failed to load existing snapshot for %s: %s", companyName, error)
			return {"jobs": []}
	else:
		return {"jobs": []}


def normalizeText(text: str) -> str:
	normalized = text.replace("\xa0", " ").strip()
	return normalized


def parseJobsFromHtml(htmlText: str) -> list:
	chunks = htmlText.split(cardMarker)
	newJobs = []
	index = 1
	while index < len(chunks):
		chunk = chunks[index]
		card = parseCardChunk(chunk)
		cardId = card.get("cardId", "")
		hasCardId = cardId != ""
		if hasCardId:
			title = normalizeText(card.get("title", ""))
			jobId = generateJobId(title, cardId)
			job = {
				"id": jobId,
				"title": title,
				"link": sourceUrl,
				"location": normalizeText(card.get("location", "")),
				"department": normalizeText(card.get("department", "")),
				"jobType": normalizeText(card.get("jobType", "")),
				"postedAt": normalizeText(card.get("postedAt", "")),
				"closingDate": normalizeText(card.get("closingDate", "")),
				"state": "open",
			}
			newJobs.append(job)
		index = index + 1
	return newJobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	htmlText = ""
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page(
				user_agent=(
					"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
					"(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
				)
			)
			await page.goto(url, wait_until="networkidle", timeout=45000)
			await page.wait_for_selector('div[name="card"]', timeout=20000)
			await page.wait_for_timeout(1500)
			previousCardCount = 0
			stableRounds = 0
			keepScrolling = True
			while keepScrolling:
				cardElements = await page.query_selector_all('div[name="card"]')
				currentCardCount = len(cardElements)
				noNewCards = currentCardCount == previousCardCount
				if noNewCards:
					stableRounds = stableRounds + 1
				else:
					stableRounds = 0
				previousCardCount = currentCardCount
				reachedStableLimit = stableRounds >= 2
				if reachedStableLimit:
					keepScrolling = False
					continue
				await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
				await page.wait_for_timeout(1500)
			htmlText = await page.content()
			await browser.close()
	except Exception as error:
		logger.warning("Failed to fetch %s: %s", companyName, error)
	jobs = parseJobsFromHtml(htmlText)
	state = {"jobs": jobs}
	return state


def parseCardChunk(chunk: str) -> dict[str, Any]:
	idMatch = re.match(r'([^"]+)"', chunk)
	cardId = ""
	if idMatch is not None:
		cardId = idMatch.group(1)
	titleMatch = titlePattern.search(chunk)
	rawTitle = ""
	if titleMatch is not None:
		rawTitle = titleMatch.group(1)
	postedAtMatch = postedAtPattern.search(chunk)
	rawPostedAt = ""
	if postedAtMatch is not None:
		rawPostedAt = postedAtMatch.group(1)
	jobTypeMatch = jobTypePattern.search(chunk)
	rawJobType = ""
	if jobTypeMatch is not None:
		rawJobType = jobTypeMatch.group(1)
	rawLocation = ""
	rawDepartment = ""
	locationMatch = locationPattern.search(chunk)
	if locationMatch is not None:
		rawLocation = locationMatch.group(1)
	departmentMatch = departmentPattern.search(chunk)
	if departmentMatch is not None:
		rawDepartment = departmentMatch.group(1)
	closingDateMatch = closingDatePattern.search(chunk)
	rawClosingDate = ""
	if closingDateMatch is not None:
		rawClosingDate = closingDateMatch.group(1)
	card = {
		"cardId": cardId,
		"title": rawTitle,
		"postedAt": rawPostedAt,
		"jobType": rawJobType,
		"location": rawLocation,
		"department": rawDepartment,
		"closingDate": rawClosingDate,
	}
	return card


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobs = state.get("jobs", [])
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("Suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
		return dict(existingSnapshot)
	snapshot = {
		"sourceUrl": sourceUrl,
		"fetchedAt": datetime.now(timezone.utc).isoformat(),
		"state": "open",
		"jobs": newJobs,
	}
	return snapshot


def writeSnapshot(snapshot: dict) -> None:
	try:
		snapshotText = json.dumps(snapshot, indent=2)
		snapshotPath.write_text(snapshotText)
	except Exception as error:
		logger.warning("Failed to write snapshot for %s: %s", companyName, error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	logging.basicConfig(level=logging.INFO)
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("Fetched %d jobs for %s", jobCount, companyName)


if __name__ == "__main__":
	asyncio.run(runMain())