import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aioapp")

sourceUrl = "https://www.aioapp.com/careers/islamabad"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "aioapp.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def extractStableId(href: str) -> str:
	segments = href.strip("/").split("/")
	hasEnoughSegments = len(segments) >= 2
	isPositionPath = hasEnoughSegments and segments[-2] == "p"
	if isPositionPath:
		lastSegment = segments[-1]
		stableId = lastSegment.split("-")[0]
	else:
		stableId = ""
	return stableId


def normalizeText(rawText: str) -> str:
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=30000)
			await page.wait_for_selector(".job-card", timeout=20000)
			cardLocator = page.locator(".job-card")
			cardCount = await cardLocator.count()
			index = 0
			while index < cardCount:
				currentCard = cardLocator.nth(index)
				titleLocator = currentCard.locator(".job-title")
				titleCount = await titleLocator.count()
				hasTitle = titleCount > 0
				if hasTitle:
					titleText = await titleLocator.first.inner_text()
					title = normalizeText(titleText)
					jobTypeLocator = currentCard.locator(".job-type")
					jobTypeCount = await jobTypeLocator.count()
					hasJobType = jobTypeCount > 0
					if hasJobType:
						jobTypeText = await jobTypeLocator.first.inner_text()
						jobType = normalizeText(jobTypeText)
					else:
						jobType = ""
					jobLevelLocator = currentCard.locator(".job-level")
					jobLevelCount = await jobLevelLocator.count()
					hasJobLevel = jobLevelCount > 0
					if hasJobLevel:
						jobLevelText = await jobLevelLocator.first.inner_text()
						jobLevel = normalizeText(jobLevelText).lstrip("•").strip()
					else:
						jobLevel = ""
					locationLocator = currentCard.locator(".job-location")
					locationCount = await locationLocator.count()
					hasLocation = locationCount > 0
					if hasLocation:
						locationText = await locationLocator.first.inner_text()
						location = normalizeText(locationText)
					else:
						location = ""
					applyLinkLocator = currentCard.locator("a.apply-button")
					applyLinkCount = await applyLinkLocator.count()
					hasApplyLink = applyLinkCount > 0
					if hasApplyLink:
						href = await applyLinkLocator.first.get_attribute("href")
						hasHref = href is not None
						if not hasHref:
							href = ""
					else:
						href = ""
					stableId = extractStableId(href)
					jobId = generateJobId(title, stableId)
					job = {
						"id": jobId,
						"title": title,
						"link": href,
						"location": location,
						"department": "",
						"jobType": jobType,
						"jobLevel": jobLevel,
						"postedAt": "",
						"state": "open",
					}
					jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("aioapp: fetchState failed: %s", error)
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
		logger.exception("aioapp: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("aioapp: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("aioapp: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("aioapp: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())