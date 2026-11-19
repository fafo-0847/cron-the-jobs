import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("visionet")

sourceUrl = "https://www.visionet.com/job"
baseUrl = "https://www.visionet.com"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "visionet.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def extractStableId(href: str) -> str:
	slug = href.strip("/").split("/")[-1]
	tokens = slug.split("-")
	hasTokens = len(tokens) > 0
	if hasTokens:
		lastToken = tokens[-1]
	else:
		lastToken = ""
	isNumeric = lastToken.isdigit()
	if isNumeric:
		stableId = lastToken
	else:
		stableId = slug
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
			await page.wait_for_selector(".service-card", timeout=20000)
			cardLocator = page.locator(".service-card")
			cardCount = await cardLocator.count()
			index = 0
			while index < cardCount:
				currentCard = cardLocator.nth(index)
				titleLocator = currentCard.locator("h2.h4")
				titleCount = await titleLocator.count()
				hasTitle = titleCount > 0
				if hasTitle:
					titleText = await titleLocator.first.inner_text()
					title = normalizeText(titleText)
					applyLinkLocator = currentCard.locator(".apply-now-link a")
					applyLinkCount = await applyLinkLocator.count()
					hasApplyLink = applyLinkCount > 0
					if hasApplyLink:
						href = await applyLinkLocator.first.get_attribute("href")
						hasHref = href is not None
						if not hasHref:
							href = ""
					else:
						href = ""
					iconSectionLocator = currentCard.locator(".icon-section span")
					iconSectionCount = await iconSectionLocator.count()
					hasExperience = iconSectionCount >= 1
					if hasExperience:
						experienceText = await iconSectionLocator.nth(0).inner_text()
						experience = normalizeText(experienceText)
					else:
						experience = ""
					hasLocation = iconSectionCount >= 2
					if hasLocation:
						locationText = await iconSectionLocator.nth(1).inner_text()
						location = normalizeText(locationText)
					else:
						location = ""
					levelLocator = currentCard.locator("h3.h5")
					levelCount = await levelLocator.count()
					hasLevel = levelCount > 0
					if hasLevel:
						levelText = await levelLocator.first.inner_text()
						jobLevel = normalizeText(levelText)
					else:
						jobLevel = ""
					stableId = extractStableId(href)
					jobId = generateJobId(title, stableId)
					link = baseUrl + href
					job = {
						"id": jobId,
						"title": title,
						"link": link,
						"location": location,
						"department": "",
						"jobType": "",
						"experience": experience,
						"jobLevel": jobLevel,
						"postedAt": "",
						"state": "open",
					}
					jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("visionet: fetchState failed: %s", error)
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
		logger.exception("visionet: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("visionet: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("visionet: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("visionet: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())