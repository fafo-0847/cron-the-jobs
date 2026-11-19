import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("powersoft19")

sourceUrl = "https://www.powersoft19.com/careers/"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "powersoft19.json"


def generateJobId(title: str) -> str:
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
			await page.goto(url, wait_until="domcontentloaded", timeout=30000)
			await page.wait_for_selector("img[src*='careers-']", timeout=20000)
			iconLocator = page.locator("img[src*='careers-']")
			iconCount = await iconLocator.count()
			index = 0
			while index < iconCount:
				currentIcon = iconLocator.nth(index)
				columnLocator = currentIcon.locator("xpath=ancestor::div[contains(@class,'wpb_column')][1]")
				columnCount = await columnLocator.count()
				hasColumn = columnCount > 0
				if hasColumn:
					titleLocator = columnLocator.first.locator("h4")
					titleCount = await titleLocator.count()
					hasTitle = titleCount > 0
					if hasTitle:
						titleText = await titleLocator.first.inner_text()
						title = normalizeText(titleText)
						hasNonEmptyTitle = title != ""
						if hasNonEmptyTitle:
							jobId = generateJobId(title)
							job = {
								"id": jobId,
								"title": title,
								"link": "",
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
		logger.exception("powersoft19: fetchState failed: %s", error)
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
		logger.exception("powersoft19: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("powersoft19: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("powersoft19: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("powersoft19: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())