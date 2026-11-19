import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("heyoz")

sourceUrl = "https://careers.heyoz.com/"
baseUrl = "https://careers.heyoz.com"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "heyoz.json"


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


def resolveLink(href: str) -> str:
	isAbsolute = href.startswith("http")
	if isAbsolute:
		return href
	isRootRelative = href.startswith("/")
	if isRootRelative:
		return baseUrl + href
	return baseUrl + "/" + href


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
				titleLinkLocator = currentCard.locator("a.job-title-link")
				titleLinkCount = await titleLinkLocator.count()
				hasTitleLink = titleLinkCount > 0
				if hasTitleLink:
					titleAttr = await titleLinkLocator.first.get_attribute("data-job-title")
					hasTitleAttr = titleAttr is not None and titleAttr != ""
					if hasTitleAttr:
						title = normalizeText(titleAttr)
					else:
						titleText = await titleLinkLocator.first.inner_text()
						title = normalizeText(titleText)
					hasNonEmptyTitle = title != ""
					if hasNonEmptyTitle:
						stableId = await titleLinkLocator.first.get_attribute("data-job-id")
						hasStableId = stableId is not None
						if not hasStableId:
							stableId = ""
						href = await titleLinkLocator.first.get_attribute("href")
						hasHref = href is not None
						if not hasHref:
							href = ""
						descriptionLocator = currentCard.locator(".jobs-description-container p")
						descriptionCount = await descriptionLocator.count()
						hasDescription = descriptionCount > 0
						if hasDescription:
							descriptionText = await descriptionLocator.first.inner_text()
							description = normalizeText(descriptionText)
						else:
							description = ""
						jobId = generateJobId(title, stableId)
						link = resolveLink(href)
						job = {
							"id": jobId,
							"title": title,
							"link": link,
							"location": "",
							"department": "",
							"jobType": "",
							"description": description,
							"postedAt": "",
							"state": "open",
						}
						jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("heyoz: fetchState failed: %s", error)
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
		logger.exception("heyoz: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("heyoz: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("heyoz: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("heyoz: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())