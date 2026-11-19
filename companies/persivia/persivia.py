import hashlib
import json
import logging
import datetime
import re
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("persivia")

sourceUrl = "https://wp.persivia.com/careers/"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "persivia.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def extractStableId(containerClass: str) -> str:
	match = re.search(r"post-(\d+)", containerClass)
	hasMatch = match is not None
	if hasMatch:
		return match.group(1)
	return ""


def normalizeText(rawText) -> str:
	isNone = rawText is None
	if isNone:
		return ""
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=30000)
			await page.wait_for_selector(".tt-job", timeout=20000)
			cardLocator = page.locator(".tt-job")
			cardCount = await cardLocator.count()
			index = 0
			while index < cardCount:
				currentCard = cardLocator.nth(index)
				containerClass = await currentCard.get_attribute("class")
				hasContainerClass = containerClass is not None
				if not hasContainerClass:
					containerClass = ""
				titleLinkLocator = currentCard.locator(".tt-job__title a")
				titleLinkCount = await titleLinkLocator.count()
				hasTitleLink = titleLinkCount > 0
				if hasTitleLink:
					titleText = await titleLinkLocator.first.inner_text()
					title = normalizeText(titleText)
					hasNonEmptyTitle = title != ""
					if hasNonEmptyTitle:
						href = await titleLinkLocator.first.get_attribute("href")
						hasHref = href is not None
						if not hasHref:
							href = ""
						jobTypeLocator = currentCard.locator(".tt-job__type-text")
						jobTypeCount = await jobTypeLocator.count()
						hasJobType = jobTypeCount > 0
						if hasJobType:
							jobTypeText = await jobTypeLocator.first.inner_text()
							jobType = normalizeText(jobTypeText)
						else:
							jobType = ""
						infoItemLocator = currentCard.locator(".tt-job__info li .tt-job__info-text")
						infoItemCount = await infoItemLocator.count()
						hasCompanyInfo = infoItemCount >= 1
						if hasCompanyInfo:
							companyText = await infoItemLocator.nth(0).inner_text()
							companyName = normalizeText(companyText)
						else:
							companyName = ""
						hasLocationInfo = infoItemCount >= 2
						if hasLocationInfo:
							locationText = await infoItemLocator.nth(1).inner_text()
							location = normalizeText(locationText)
						else:
							location = ""
						stableId = extractStableId(containerClass)
						jobId = generateJobId(title, stableId)
						job = {
							"id": jobId,
							"title": title,
							"link": href,
							"location": location,
							"department": companyName,
							"jobType": jobType,
							"postedAt": "",
							"state": "open",
						}
						jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("persivia: fetchState failed: %s", error)
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
		logger.exception("persivia: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("persivia: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("persivia: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("persivia: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())