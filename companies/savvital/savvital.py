import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("savvital")

sourceUrl = "https://savvital.breezy.hr"
baseUrl = "https://savvital.breezy.hr"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "savvital.json"


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
	hasEnoughSegments = len(segments) >= 2
	isPositionPath = hasEnoughSegments and segments[0] == "p"
	if isPositionPath:
		lastSegment = segments[-1]
		stableId = lastSegment.split("-")[0]
	else:
		stableId = ""
	return stableId


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
			await page.wait_for_selector("li.position", timeout=20000)
			groupHeadingLocator = page.locator("h2.group-header")
			groupHeadingCount = await groupHeadingLocator.count()
			groupIndex = 0
			while groupIndex < groupHeadingCount:
				currentHeading = groupHeadingLocator.nth(groupIndex)
				countryLocator = currentHeading.locator("span")
				countryCount = await countryLocator.count()
				hasCountry = countryCount > 0
				if hasCountry:
					countryText = await countryLocator.first.inner_text()
					country = normalizeText(countryText)
				else:
					country = ""
				siblingListLocator = currentHeading.locator("xpath=following-sibling::ul[1]")
				positionLocator = siblingListLocator.locator("li.position")
				positionCount = await positionLocator.count()
				positionIndex = 0
				while positionIndex < positionCount:
					currentPosition = positionLocator.nth(positionIndex)
					titleLocator = currentPosition.locator(".position-details a h2")
					titleCount = await titleLocator.count()
					hasTitle = titleCount > 0
					if hasTitle:
						titleText = await titleLocator.first.inner_text()
						title = normalizeText(titleText)
						anchorLocator = currentPosition.locator(".position-details a")
						anchorCount = await anchorLocator.count()
						hasAnchor = anchorCount > 0
						if hasAnchor:
							href = await anchorLocator.first.get_attribute("href")
							hasHref = href is not None
							if not hasHref:
								href = ""
						else:
							href = ""
						metaLocationLocator = currentPosition.locator("li.location span")
						metaLocationCount = await metaLocationLocator.count()
						hasMetaLocation = metaLocationCount > 0
						if hasMetaLocation:
							locationText = await metaLocationLocator.first.inner_text()
							location = normalizeText(locationText)
						else:
							location = ""
						hasRemoteType = metaLocationCount >= 2
						if hasRemoteType:
							remoteTypeText = await metaLocationLocator.nth(1).inner_text()
							remoteType = normalizeText(remoteTypeText)
						else:
							remoteType = ""
						typeLocator = currentPosition.locator("li.type span")
						typeCount = await typeLocator.count()
						hasType = typeCount > 0
						if hasType:
							typeText = await typeLocator.first.inner_text()
							jobType = normalizeText(typeText)
						else:
							jobType = ""
						stableId = extractStableId(href)
						jobId = generateJobId(title, stableId)
						link = baseUrl + href
						job = {
							"id": jobId,
							"title": title,
							"link": link,
							"location": location,
							"department": country,
							"jobType": jobType,
							"remoteType": remoteType,
							"postedAt": "",
							"state": "open",
						}
						jobs.append(job)
					positionIndex = positionIndex + 1
				groupIndex = groupIndex + 1
			await browser.close()
	except Exception as error:
		logger.exception("savvital: fetchState failed: %s", error)
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
		logger.exception("savvital: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("savvital: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("savvital: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("savvital: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())