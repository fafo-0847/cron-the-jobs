import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("justappraised")

sourceUrl = "https://ats.rippling.com/just-appraised-jobs/jobs"
baseUrl = "https://ats.rippling.com"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "justappraised.json"


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
	hasSegments = len(segments) > 0
	if hasSegments:
		stableId = segments[-1]
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
			await page.wait_for_selector("a[href*='/jobs/']", timeout=20000)
			headingLocator = page.locator("h3")
			headingCount = await headingLocator.count()
			headingIndex = 0
			while headingIndex < headingCount:
				currentHeading = headingLocator.nth(headingIndex)
				headingText = await currentHeading.inner_text()
				groupName = normalizeText(headingText)
				siblingLocator = currentHeading.locator("xpath=following-sibling::div[1]")
				anchorLocator = siblingLocator.locator("a[href*='/jobs/']:not(:has(button))")
				anchorCount = await anchorLocator.count()
				anchorIndex = 0
				while anchorIndex < anchorCount:
					currentAnchor = anchorLocator.nth(anchorIndex)
					titleText = await currentAnchor.inner_text()
					title = normalizeText(titleText)
					hasTitle = title != ""
					if hasTitle:
						href = await currentAnchor.get_attribute("href")
						hasHref = href is not None
						if not hasHref:
							href = ""
						entryLocator = currentAnchor.locator("xpath=ancestor::div[3]")
						departmentIconLocator = entryLocator.locator("div:has(span[data-icon='DEPARTMENTS_OUTLINE'])")
						departmentIconCount = await departmentIconLocator.count()
						hasDepartmentIcon = departmentIconCount > 0
						if hasDepartmentIcon:
							departmentText = await departmentIconLocator.first.locator("p").first.inner_text()
							department = normalizeText(departmentText)
						else:
							department = groupName
						locationIconLocator = entryLocator.locator("div:has(span[data-icon='LOCATION_OUTLINE'])")
						locationIconCount = await locationIconLocator.count()
						hasLocationIcon = locationIconCount > 0
						if hasLocationIcon:
							locationText = await locationIconLocator.first.locator("p").first.inner_text()
							location = normalizeText(locationText)
						else:
							location = ""
						stableId = extractStableId(href)
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
					anchorIndex = anchorIndex + 1
				headingIndex = headingIndex + 1
			await browser.close()
	except Exception as error:
		logger.exception("justappraised: fetchState failed: %s", error)
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
		logger.exception("justappraised: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("justappraised: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("justappraised: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("justappraised: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())