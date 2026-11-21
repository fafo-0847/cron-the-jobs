import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from companies._shared import browser as sharedBrowser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("infotech")

sourceUrl = "https://infotechgroup.com/jobs-at-infotech/"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "infotech.json"


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
	seenIds = set()
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await sharedBrowser.newPage(browser)
			await sharedBrowser.gotoChecked(page, url, waitUntil="domcontentloaded", timeoutMs=30000)
			await page.wait_for_selector(".ld-fancy-heading h3 a", timeout=20000)
			titleLinkLocator = page.locator(".ld-fancy-heading h3 a")
			titleLinkCount = await titleLinkLocator.count()
			index = 0
			while index < titleLinkCount:
				currentLink = titleLinkLocator.nth(index)
				titleText = await currentLink.inner_text()
				title = normalizeText(titleText)
				hasTitle = title != ""
				if hasTitle:
					href = await currentLink.get_attribute("href")
					hasHref = href is not None
					if not hasHref:
						href = ""
					stableId = extractStableId(href)
					alreadySeen = stableId in seenIds
					if not alreadySeen:
						seenIds.add(stableId)
						jobId = generateJobId(title, stableId)
						job = {
							"id": jobId,
							"title": title,
							"link": href,
							"location": "",
							"department": "",
							"jobType": "",
							"postedAt": "",
							"state": "open",
						}
						jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("infotech: fetchState failed: %s", error)
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
		logger.exception("infotech: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("infotech: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("infotech: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("infotech: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())