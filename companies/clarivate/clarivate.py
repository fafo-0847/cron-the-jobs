import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("clarivate")

sourceUrl = "https://careers.clarivate.com/c/technology-jobs"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "clarivate.json"
maxPages = 30


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def normalizeText(rawText: str) -> str:
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


async def extractFieldText(cardLocator, fieldId: str) -> str:
	fieldValue = ""
	try:
		fieldLocator = cardLocator.locator(f"[data-ph-at-id='{fieldId}']")
		fieldCount = await fieldLocator.count()
		hasField = fieldCount > 0
		if hasField:
			spanLocator = fieldLocator.first.locator("span")
			spanCount = await spanLocator.count()
			hasSpans = spanCount > 0
			if hasSpans:
				spanText = await spanLocator.last.inner_text()
				fieldValue = normalizeText(spanText)
	except Exception as error:
		logger.exception("clarivate: extractFieldText failed for %s: %s", fieldId, error)
	return fieldValue


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
				await page.wait_for_selector("a[data-ph-at-id='job-link']", timeout=20000)
				jobLinkLocator = page.locator("a[data-ph-at-id='job-link']")
				jobLinkCount = await jobLinkLocator.count()
				jobIndex = 0
				while jobIndex < jobLinkCount:
					currentLink = jobLinkLocator.nth(jobIndex)
					titleAttr = await currentLink.get_attribute("data-ph-at-job-title-text")
					hasTitleAttr = titleAttr is not None
					if not hasTitleAttr:
						titleAttr = ""
					title = normalizeText(titleAttr)
					hasTitle = title != ""
					if hasTitle:
						jobIdAttr = await currentLink.get_attribute("data-ph-at-job-id-text")
						hasJobIdAttr = jobIdAttr is not None
						if not hasJobIdAttr:
							jobIdAttr = ""
						stableId = normalizeText(jobIdAttr)
						href = await currentLink.get_attribute("href")
						hasHref = href is not None
						if not hasHref:
							href = ""
						cardLocator = currentLink.locator("xpath=ancestor::div[@role='listitem'][1]")
						location = await extractFieldText(cardLocator, "job-location")
						segment = await extractFieldText(cardLocator, "job-segment")
						remoteType = await extractFieldText(cardLocator, "job-remote")
						jobId = generateJobId(title, stableId)
						job = {
							"id": jobId,
							"title": title,
							"link": href,
							"location": location,
							"department": segment,
							"jobType": remoteType,
							"jobCode": stableId,
							"postedAt": "",
							"state": "open",
						}
						jobs.append(job)
					jobIndex = jobIndex + 1
				nextLinkLocator = page.locator("a[data-ph-at-id='pagination-next-link']")
				nextLinkCount = await nextLinkLocator.count()
				hasNextLink = nextLinkCount > 0
				if hasNextLink:
					isNextVisible = await nextLinkLocator.first.is_visible()
					if isNextVisible:
						nextHref = await nextLinkLocator.first.get_attribute("href")
						hasNextHref = nextHref is not None and nextHref != ""
						if hasNextHref:
							currentUrl = nextHref
							keepGoing = True
						else:
							keepGoing = False
					else:
						keepGoing = False
				else:
					keepGoing = False
				pageIndex = pageIndex + 1
			await browser.close()
	except Exception as error:
		logger.exception("clarivate: fetchState failed: %s", error)
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
		logger.exception("clarivate: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("clarivate: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("clarivate: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("clarivate: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())