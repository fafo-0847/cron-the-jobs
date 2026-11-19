import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("halliburton")

sourceUrl = "https://careers.halliburton.com/category/engineering-science-technology-jobs/543/8646032/1"
baseUrl = "https://careers.halliburton.com"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "halliburton.json"
maxPages = 30


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


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			currentUrl = url
			pageIndex = 0
			keepGoing = True
			while keepGoing and pageIndex < maxPages:
				await page.goto(currentUrl, wait_until="domcontentloaded", timeout=30000)
				await page.wait_for_selector("#search-results-list a[data-job-id]", timeout=20000)
				jobLinkLocator = page.locator("#search-results-list a[data-job-id]")
				jobLinkCount = await jobLinkLocator.count()
				jobIndex = 0
				while jobIndex < jobLinkCount:
					currentLink = jobLinkLocator.nth(jobIndex)
					titleLocator = currentLink.locator("h2")
					titleCount = await titleLocator.count()
					hasTitle = titleCount > 0
					if hasTitle:
						titleText = await titleLocator.first.inner_text()
						title = normalizeText(titleText)
						hasNonEmptyTitle = title != ""
						if hasNonEmptyTitle:
							stableId = await currentLink.get_attribute("data-job-id")
							hasStableId = stableId is not None
							if not hasStableId:
								stableId = ""
							href = await currentLink.get_attribute("href")
							hasHref = href is not None
							if not hasHref:
								href = ""
							locationLocator = currentLink.locator(".job-location")
							locationCount = await locationLocator.count()
							hasLocation = locationCount > 0
							if hasLocation:
								locationText = await locationLocator.first.inner_text()
								location = normalizeText(locationText)
							else:
								location = ""
							categoryLocator = currentLink.locator(".job-jobCategories")
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
								"postedAt": "",
								"state": "open",
							}
							jobs.append(job)
					jobIndex = jobIndex + 1
				nextLinkLocator = page.locator("#pagination-bottom a.next")
				nextLinkCount = await nextLinkLocator.count()
				hasNextLink = nextLinkCount > 0
				if hasNextLink:
					nextClassAttr = await nextLinkLocator.first.get_attribute("class")
					hasNextClassAttr = nextClassAttr is not None
					if not hasNextClassAttr:
						nextClassAttr = ""
					isDisabled = "disabled" in nextClassAttr
					if isDisabled:
						keepGoing = False
					else:
						nextHref = await nextLinkLocator.first.get_attribute("href")
						hasNextHref = nextHref is not None and nextHref != ""
						if hasNextHref:
							currentUrl = baseUrl + nextHref
							keepGoing = True
						else:
							keepGoing = False
				else:
					keepGoing = False
				pageIndex = pageIndex + 1
			await browser.close()
	except Exception as error:
		logger.exception("halliburton: fetchState failed: %s", error)
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
		logger.exception("halliburton: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("halliburton: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("halliburton: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("halliburton: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())