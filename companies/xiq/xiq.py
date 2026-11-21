import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from companies._shared import browser as sharedBrowser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("xiq")

sourceUrl = "https://xiqinc.com/careers/"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "xiq.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def extractStableId(containerId: str) -> str:
	prefix = "awsm-grid-item-"
	hasPrefix = containerId.startswith(prefix)
	if hasPrefix:
		stableId = containerId[len(prefix):]
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
			page = await sharedBrowser.newPage(browser)
			await sharedBrowser.gotoChecked(page, url, waitUntil="domcontentloaded", timeoutMs=30000)
			await page.wait_for_selector(".awsm-job-listing-item", timeout=20000)
			itemLocator = page.locator(".awsm-job-listing-item")
			itemCount = await itemLocator.count()
			index = 0
			while index < itemCount:
				currentItem = itemLocator.nth(index)
				containerId = await currentItem.get_attribute("id")
				hasContainerId = containerId is not None
				if not hasContainerId:
					containerId = ""
				linkLocator = currentItem.locator("a.awsm-job-item")
				linkCount = await linkLocator.count()
				hasLink = linkCount > 0
				if hasLink:
					href = await linkLocator.first.get_attribute("href")
					hasHref = href is not None
					if not hasHref:
						href = ""
					titleLocator = currentItem.locator("h2.awsm-job-post-title")
					titleCount = await titleLocator.count()
					hasTitle = titleCount > 0
					if hasTitle:
						titleText = await titleLocator.first.inner_text()
						title = normalizeText(titleText)
						jobTypeLocator = currentItem.locator(".awsm-job-specification-job-type .awsm-job-specification-term")
						jobTypeCount = await jobTypeLocator.count()
						hasJobType = jobTypeCount > 0
						if hasJobType:
							jobTypeText = await jobTypeLocator.first.inner_text()
							jobType = normalizeText(jobTypeText)
						else:
							jobType = ""
						locationLocator = currentItem.locator(".awsm-job-specification-location .awsm-job-specification-term")
						locationCount = await locationLocator.count()
						hasLocation = locationCount > 0
						if hasLocation:
							locationText = await locationLocator.first.inner_text()
							location = normalizeText(locationText)
						else:
							location = ""
						stableId = extractStableId(containerId)
						jobId = generateJobId(title, stableId)
						job = {
							"id": jobId,
							"title": title,
							"link": href,
							"location": location,
							"department": "",
							"jobType": jobType,
							"postedAt": "",
							"state": "open",
						}
						jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("xiq: fetchState failed: %s", error)
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
		logger.exception("xiq: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("xiq: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("xiq: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("xiq: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())