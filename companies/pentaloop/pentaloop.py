import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pentaloop")

sourceUrl = "https://pentaloop.com/view-job-openings/"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "pentaloop.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def extractStableId(containerId: str) -> str:
	prefix = "awsm-list-item-"
	hasPrefix = containerId.startswith(prefix)
	if hasPrefix:
		stableId = containerId[len(prefix):]
	else:
		stableId = ""
	return stableId


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=30000)
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
				titleLinkLocator = currentItem.locator("h2.awsm-job-post-title a")
				titleLinkCount = await titleLinkLocator.count()
				hasTitleLink = titleLinkCount > 0
				if hasTitleLink:
					title = await titleLinkLocator.first.inner_text()
					link = await titleLinkLocator.first.get_attribute("href")
					hasLink = link is not None
					if not hasLink:
						link = ""
					categoryLocator = currentItem.locator(".awsm-job-specification-term")
					categoryCount = await categoryLocator.count()
					hasCategory = categoryCount > 0
					if hasCategory:
						category = await categoryLocator.first.inner_text()
					else:
						category = ""
					stableId = extractStableId(containerId)
					cleanTitle = title.replace("\xa0", " ").strip()
					jobId = generateJobId(cleanTitle, stableId)
					job = {
						"id": jobId,
						"title": cleanTitle,
						"link": link,
						"location": "",
						"department": category.strip(),
						"jobType": "",
						"postedAt": "",
						"state": "open",
					}
					jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("pentaloop: fetchState failed: %s", error)
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
		logger.exception("pentaloop: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("pentaloop: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("pentaloop: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("pentaloop: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())