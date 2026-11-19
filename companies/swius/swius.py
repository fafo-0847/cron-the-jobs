import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("swius")

sourceUrl = "https://swius.com/wp-content/plugins/bullhorn-oscp-swi/#/"
baseUrl = "https://swius.com"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "swius.json"
maxScrollRounds = 60
stableRoundsNeeded = 3
scrollPauseMs = 1500


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def normalizeText(rawText) -> str:
	isNone = rawText is None
	if isNone:
		return ""
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


def extractJobIdNumber(bhJidText: str) -> str:
	normalized = normalizeText(bhJidText)
	prefix = "Job Id:"
	hasPrefix = normalized.startswith(prefix)
	if hasPrefix:
		stableId = normalized[len(prefix):].strip()
	else:
		stableId = normalized
	return stableId


async def scrollUntilStable(page) -> None:
	previousCount = -1
	stableRounds = 0
	roundIndex = 0
	while roundIndex < maxScrollRounds and stableRounds < stableRoundsNeeded:
		cardLocator = page.locator(".job-card")
		currentCount = await cardLocator.count()
		didNotGrow = currentCount == previousCount
		if didNotGrow:
			stableRounds = stableRounds + 1
		else:
			stableRounds = 0
		previousCount = currentCount
		hasCards = currentCount > 0
		if hasCards:
			await cardLocator.last.scroll_into_view_if_needed()
		await page.wait_for_timeout(scrollPauseMs)
		roundIndex = roundIndex + 1


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=30000)
			await page.wait_for_selector(".job-card", timeout=20000)
			await scrollUntilStable(page)
			cardLocator = page.locator(".job-card")
			cardCount = await cardLocator.count()
			logger.info("swius: %d job cards loaded after scrolling", cardCount)
			index = 0
			while index < cardCount:
				currentCard = cardLocator.nth(index)
				titleLinkLocator = currentCard.locator("h6 a")
				titleLinkCount = await titleLinkLocator.count()
				hasTitleLink = titleLinkCount > 0
				if hasTitleLink:
					titleText = await titleLinkLocator.first.inner_text()
					title = normalizeText(titleText)
					href = await titleLinkLocator.first.get_attribute("href")
					hasHref = href is not None
					if not hasHref:
						href = ""
					bhJidLocator = currentCard.locator(".bh-jid")
					bhJidCount = await bhJidLocator.count()
					hasBhJid = bhJidCount > 0
					if hasBhJid:
						bhJidText = await bhJidLocator.first.inner_text()
						stableId = extractJobIdNumber(bhJidText)
					else:
						stableId = ""
					locationLocator = currentCard.locator("[data-automation-id='chip-address']")
					locationCount = await locationLocator.count()
					hasLocation = locationCount > 0
					if hasLocation:
						locationText = await locationLocator.first.inner_text()
						location = normalizeText(locationText)
					else:
						location = ""
					dateLocator = currentCard.locator("[data-automation-id='chip-dateLastPublished']")
					dateCount = await dateLocator.count()
					hasDate = dateCount > 0
					if hasDate:
						dateText = await dateLocator.first.inner_text()
						postedAt = normalizeText(dateText)
					else:
						postedAt = ""
					categoryLocator = currentCard.locator(".category")
					categoryCount = await categoryLocator.count()
					hasCategory = categoryCount > 0
					if hasCategory:
						categoryText = await categoryLocator.first.inner_text()
						department = normalizeText(categoryText)
					else:
						department = ""
					jobId = generateJobId(title, stableId)
					link = baseUrl + href
					job = {
						"id": jobId,
						"title": title,
						"link": link,
						"location": location,
						"department": department,
						"jobType": "",
						"jobCode": stableId,
						"postedAt": postedAt,
						"state": "open",
					}
					jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("swius: fetchState failed: %s", error)
	state = {"jobs": jobs, "state": "open"}
	return state


def loadExistingSnapshot() -> dict[str, Any]:
	try:
		fileExists = snapshotPath.exists()
		if not fileExists:
			return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}
		rawText = snapshotPath.read_text(encoding="utf-8")
		snapshot = json.loads(rawText)
		return snapshot
	except Exception as error:
		logger.exception("swius: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("swius: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
		return dict(existingSnapshot)
	fetchedAt = datetime.datetime.now(datetime.timezone.utc).isoformat()
	snapshot = {
		"sourceUrl": sourceUrl,
		"fetchedAt": fetchedAt,
		"state": state.get("state", "open"),
		"jobs": newJobs,
	}
	return snapshot


def writeSnapshot(snapshot: dict) -> None:
	try:
		snapshotText = json.dumps(snapshot, indent=2, ensure_ascii=False)
		snapshotPath.write_text(snapshotText, encoding="utf-8")
	except Exception as error:
		logger.exception("swius: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("swius: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())