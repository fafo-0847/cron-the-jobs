import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cloudelligent")

sourceUrl = "https://cloudelligent.com/careers/"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "cloudelligent.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def extractStableId(containerId: str) -> str:
	prefix = "resumator-job-"
	hasPrefix = containerId.startswith(prefix)
	if hasPrefix:
		stableId = containerId[len(prefix):]
	else:
		stableId = ""
	return stableId


def normalizeText(rawText) -> str:
	isNone = rawText is None
	if isNone:
		return ""
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


def stripLabel(rawText: str) -> str:
	normalized = normalizeText(rawText)
	hasColon = ":" in normalized
	if hasColon:
		parts = normalized.split(":", 1)
		result = parts[1].strip()
	else:
		result = normalized
	return result


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=30000)
			await page.wait_for_selector(".resumator-job", timeout=20000)
			cardLocator = page.locator(".resumator-job")
			cardCount = await cardLocator.count()
			index = 0
			while index < cardCount:
				currentCard = cardLocator.nth(index)
				containerId = await currentCard.get_attribute("id")
				hasContainerId = containerId is not None
				if not hasContainerId:
					containerId = ""
				titleLocator = currentCard.locator(".resumator-job-title")
				titleCount = await titleLocator.count()
				hasTitle = titleCount > 0
				if hasTitle:
					titleText = await titleLocator.first.inner_text()
					title = normalizeText(titleText)
					hasNonEmptyTitle = title != ""
					if hasNonEmptyTitle:
						locationLocator = currentCard.locator(".resumator-job-info")
						locationCount = await locationLocator.count()
						hasLocation = locationCount > 0
						if hasLocation:
							locationText = await locationLocator.first.inner_text()
							location = stripLabel(locationText)
						else:
							location = ""
						linkLocator = currentCard.locator("a.resumator-job-link")
						linkCount = await linkLocator.count()
						hasLink = linkCount > 0
						if hasLink:
							href = await linkLocator.first.get_attribute("href")
							hasHref = href is not None
							if not hasHref:
								href = ""
						else:
							href = ""
						stableId = extractStableId(containerId)
						jobId = generateJobId(title, stableId)
						job = {
							"id": jobId,
							"title": title,
							"link": href,
							"location": location,
							"department": "",
							"jobType": "",
							"postedAt": "",
							"state": "open",
						}
						jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("cloudelligent: fetchState failed: %s", error)
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
		logger.exception("cloudelligent: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("cloudelligent: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("cloudelligent: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("cloudelligent: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())