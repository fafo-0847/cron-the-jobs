import hashlib
import json
import logging
import datetime
import re
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("colabs")

sourceUrl = "https://www.colabs.pk/careers"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "colabs.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def extractStableId(href: str) -> str:
	isGoogleForm = "docs.google.com/forms" in href
	if isGoogleForm:
		match = re.search(r"/forms/d/e/([^/]+)/", href)
		hasMatch = match is not None
		if hasMatch:
			return match.group(1)
		match = re.search(r"/forms/d/([^/]+)/", href)
		hasMatch = match is not None
		if hasMatch:
			return match.group(1)
	return href


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
			await page.wait_for_selector(".jobs_item", timeout=20000)
			cardLocator = page.locator(".jobs_item")
			cardCount = await cardLocator.count()
			index = 0
			while index < cardCount:
				currentCard = cardLocator.nth(index)
				titleLinkLocator = currentCard.locator("a.jobs_link h3")
				titleLinkCount = await titleLinkLocator.count()
				hasTitleLink = titleLinkCount > 0
				if hasTitleLink:
					titleText = await titleLinkLocator.first.inner_text()
					title = normalizeText(titleText)
					hasNonEmptyTitle = title != ""
					if hasNonEmptyTitle:
						applyLinkLocator = currentCard.locator("a.jobs_link")
						applyLinkCount = await applyLinkLocator.count()
						hasApplyLink = applyLinkCount > 0
						if hasApplyLink:
							href = await applyLinkLocator.first.get_attribute("href")
							hasHref = href is not None
							if not hasHref:
								href = ""
						else:
							href = ""
						departmentLocator = currentCard.locator("[fs-cmsfilter-field='department']")
						departmentCount = await departmentLocator.count()
						hasDepartment = departmentCount > 0
						if hasDepartment:
							departmentText = await departmentLocator.first.inner_text()
							department = normalizeText(departmentText)
						else:
							department = ""
						locationLocator = currentCard.locator(":scope > div").nth(1)
						location = ""
						try:
							locationText = await locationLocator.inner_text()
							location = normalizeText(locationText)
						except Exception as locationError:
							location = ""
						stableId = extractStableId(href)
						jobId = generateJobId(title, stableId)
						job = {
							"id": jobId,
							"title": title,
							"link": href,
							"location": location,
							"department": department,
							"jobType": "",
							"postedAt": "",
							"state": "open",
						}
						jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("colabs: fetchState failed: %s", error)
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
		logger.exception("colabs: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("colabs: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("colabs: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("colabs: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())