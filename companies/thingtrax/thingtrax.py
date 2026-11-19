import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("thingtrax")

sourceUrl = "https://thingtrax.com/careers/"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "thingtrax.json"


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
			await page.wait_for_selector("li.whr-item", timeout=20000)
			groupHeadingLocator = page.locator("h2.whr-group")
			groupHeadingCount = await groupHeadingLocator.count()
			groupIndex = 0
			while groupIndex < groupHeadingCount:
				currentHeading = groupHeadingLocator.nth(groupIndex)
				countryText = await currentHeading.inner_text()
				country = normalizeText(countryText)
				siblingListLocator = currentHeading.locator("xpath=following-sibling::ul[1]")
				itemLocator = siblingListLocator.locator("li.whr-item")
				itemCount = await itemLocator.count()
				itemIndex = 0
				while itemIndex < itemCount:
					currentItem = itemLocator.nth(itemIndex)
					titleLinkLocator = currentItem.locator("h3.whr-title a")
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
							deptLocator = currentItem.locator("li.whr-dept")
							deptCount = await deptLocator.count()
							hasDept = deptCount > 0
							if hasDept:
								deptText = await deptLocator.first.inner_text()
								department = stripLabel(deptText)
							else:
								department = ""
							locationLocator = currentItem.locator("li.whr-location")
							locationCount = await locationLocator.count()
							hasLocation = locationCount > 0
							if hasLocation:
								locationText = await locationLocator.first.inner_text()
								location = stripLabel(locationText)
							else:
								location = ""
							dateLocator = currentItem.locator("li.whr-date")
							dateCount = await dateLocator.count()
							hasDate = dateCount > 0
							if hasDate:
								dateText = await dateLocator.first.inner_text()
								postedAt = stripLabel(dateText)
							else:
								postedAt = ""
							stableId = extractStableId(href)
							jobId = generateJobId(title, stableId)
							job = {
								"id": jobId,
								"title": title,
								"link": href,
								"location": location,
								"department": department,
								"jobType": "",
								"country": country,
								"postedAt": postedAt,
								"state": "open",
							}
							jobs.append(job)
					itemIndex = itemIndex + 1
				groupIndex = groupIndex + 1
			await browser.close()
	except Exception as error:
		logger.exception("thingtrax: fetchState failed: %s", error)
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
		logger.exception("thingtrax: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("thingtrax: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("thingtrax: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("thingtrax: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())