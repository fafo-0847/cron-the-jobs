import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fiveriverstech")

sourceUrl = "https://fiveriverstech.zohorecruit.com/jobs/Careers"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "fiveriverstech.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def extractStableId(href: str) -> str:
	segments = href.split("/")
	stableId = ""
	index = 0
	while index < len(segments):
		segment = segments[index]
		isLongNumeric = segment.isdigit() and len(segment) >= 10
		if isLongNumeric:
			stableId = segment
		index = index + 1
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
			await page.wait_for_selector(".jobcard-item", timeout=20000)
			cardLocator = page.locator(".jobcard-item")
			cardCount = await cardLocator.count()
			index = 0
			while index < cardCount:
				currentCard = cardLocator.nth(index)
				titleLinkLocator = currentCard.locator("a.cw-2-title")
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
						locationLocator = currentCard.locator("h3 + p")
						locationCount = await locationLocator.count()
						hasLocation = locationCount > 0
						if hasLocation:
							locationText = await locationLocator.first.inner_text()
							location = normalizeText(locationText)
						else:
							location = ""
						experienceLocator = currentCard.locator(".cw-exp-years")
						experienceCount = await experienceLocator.count()
						hasExperience = experienceCount > 0
						if hasExperience:
							experienceText = await experienceLocator.first.inner_text()
							experience = normalizeText(experienceText)
						else:
							experience = ""
						descriptionLocator = currentCard.locator(".card-text")
						descriptionCount = await descriptionLocator.count()
						hasDescription = descriptionCount > 0
						if hasDescription:
							descriptionText = await descriptionLocator.first.inner_text()
							description = normalizeText(descriptionText)
						else:
							description = ""
						jobTypeLocator = currentCard.locator(".cw-full-time")
						jobTypeCount = await jobTypeLocator.count()
						hasJobType = jobTypeCount > 0
						if hasJobType:
							jobTypeText = await jobTypeLocator.first.inner_text()
							jobType = normalizeText(jobTypeText)
						else:
							jobType = ""
						postDateLocator = currentCard.locator(".cw-post-date")
						postDateCount = await postDateLocator.count()
						hasPostDate = postDateCount > 0
						if hasPostDate:
							postDateText = await postDateLocator.first.inner_text()
							postedAt = normalizeText(postDateText)
						else:
							postedAt = ""
						stableId = extractStableId(href)
						jobId = generateJobId(title, stableId)
						job = {
							"id": jobId,
							"title": title,
							"link": href,
							"location": location,
							"department": "",
							"jobType": jobType,
							"experience": experience,
							"description": description,
							"postedAt": postedAt,
							"state": "open",
						}
						jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("fiveriverstech: fetchState failed: %s", error)
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
		logger.exception("fiveriverstech: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("fiveriverstech: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("fiveriverstech: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("fiveriverstech: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())