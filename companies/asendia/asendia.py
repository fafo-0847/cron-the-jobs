import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from companies._shared import browser as sharedBrowser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("asendia")

disabledReason = '2026-11: asendia.ai/jobs-board returns 404 and jobseeker.asendia.ai no longer resolves; no careers page found.'
sourceUrl = "https://asendia.ai/jobs-board"
baseUrl = "https://asendia.ai"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "asendia.json"
cardSelector = ".rounded-2xl.shadow-sm.border.border-gray-100"


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


async def extractStableIdFromCard(cardLocator) -> str:
	stableId = ""
	anchorLocator = cardLocator.locator("a[href]")
	anchorCount = await anchorLocator.count()
	hasAnchor = anchorCount > 0
	if hasAnchor:
		href = await anchorLocator.first.get_attribute("href")
		hasHref = href is not None and href != ""
		if hasHref:
			stableId = href
	hasStableId = stableId != ""
	if not hasStableId:
		dataIdLocator = cardLocator.locator("[data-job-id]")
		dataIdCount = await dataIdLocator.count()
		hasDataId = dataIdCount > 0
		if hasDataId:
			dataIdValue = await dataIdLocator.first.get_attribute("data-job-id")
			hasDataIdValue = dataIdValue is not None and dataIdValue != ""
			if hasDataIdValue:
				stableId = dataIdValue
	hasStableId = stableId != ""
	if not hasStableId:
		positionIdLocator = cardLocator.locator("[data-position-id]")
		positionIdCount = await positionIdLocator.count()
		hasPositionId = positionIdCount > 0
		if hasPositionId:
			positionIdValue = await positionIdLocator.first.get_attribute("data-position-id")
			hasPositionIdValue = positionIdValue is not None and positionIdValue != ""
			if hasPositionIdValue:
				stableId = positionIdValue
	return stableId


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await sharedBrowser.newPage(browser)
			await sharedBrowser.gotoChecked(page, url, waitUntil="domcontentloaded", timeoutMs=30000)
			await page.wait_for_selector(cardSelector, timeout=20000)
			cardLocator = page.locator(cardSelector)
			cardCount = await cardLocator.count()
			index = 0
			while index < cardCount:
				currentCard = cardLocator.nth(index)
				titleLocator = currentCard.locator("h2")
				titleCount = await titleLocator.count()
				hasTitle = titleCount > 0
				if hasTitle:
					titleText = await titleLocator.first.inner_text()
					title = normalizeText(titleText)
					hasNonEmptyTitle = title != ""
					if hasNonEmptyTitle:
						stableId = await extractStableIdFromCard(currentCard)
						isRealJobPosting = stableId != ""
						if isRealJobPosting:
							link = stableId
							isAbsoluteLink = link.startswith("http")
							if not isAbsoluteLink:
								link = baseUrl + link
							jobId = generateJobId(title, stableId)
							job = {
								"id": jobId,
								"title": title,
								"link": link,
								"location": "",
								"department": "",
								"jobType": "",
								"postedAt": "",
								"state": "open",
							}
							jobs.append(job)
						else:
							logger.info("asendia: skipping non-job CTA card '%s' (no identifier found)", title)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("asendia: fetchState failed: %s", error)
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
		logger.exception("asendia: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("asendia: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("asendia: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("asendia: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())