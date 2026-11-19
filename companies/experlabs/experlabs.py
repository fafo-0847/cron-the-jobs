import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("experlabs")

sourceUrl = "https://jobs.experlabs.com/jobs?location=%5B%5D&department=%5B%5D&jobType=%5B%5D&title=&isRemoteLocation=false"
baseUrl = "https://jobs.experlabs.com"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "experlabs.json"


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
	isJobsPath = hasEnoughSegments and segments[0] == "jobs"
	if isJobsPath:
		stableId = segments[1]
	else:
		stableId = ""
	return stableId


def normalizeCategory(rawText: str) -> str:
	normalized = rawText.replace("\xa0", " ").strip()
	parts = normalized.split("-")
	category = parts[0].strip()
	return category


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=30000)
			await page.wait_for_selector("a.heading[data-portal-title]", timeout=20000)
			groupLocator = page.locator("li[data-portal-role]")
			groupCount = await groupLocator.count()
			groupIndex = 0
			while groupIndex < groupCount:
				currentGroup = groupLocator.nth(groupIndex)
				headingLocator = currentGroup.locator("h5")
				headingCount = await headingLocator.count()
				hasHeading = headingCount > 0
				if hasHeading:
					headingText = await headingLocator.first.inner_text()
					category = normalizeCategory(headingText)
				else:
					category = ""
				jobAnchorLocator = currentGroup.locator("a.heading[data-portal-title]")
				jobAnchorCount = await jobAnchorLocator.count()
				jobIndex = 0
				while jobIndex < jobAnchorCount:
					currentAnchor = jobAnchorLocator.nth(jobIndex)
					href = await currentAnchor.get_attribute("href")
					hasHref = href is not None
					if not hasHref:
						href = ""
					location = await currentAnchor.get_attribute("data-portal-location")
					hasLocation = location is not None
					if not hasLocation:
						location = ""
					jobType = await currentAnchor.get_attribute("data-portal-job-type")
					hasJobType = jobType is not None
					if not hasJobType:
						jobType = ""
					titleLocator = currentAnchor.locator(".job-title")
					titleCount = await titleLocator.count()
					hasTitle = titleCount > 0
					if hasTitle:
						titleText = await titleLocator.first.inner_text()
						title = titleText.replace("\xa0", " ").strip()
						stableId = extractStableId(href)
						jobId = generateJobId(title, stableId)
						link = baseUrl + href
						job = {
							"id": jobId,
							"title": title,
							"link": link,
							"location": location.strip(),
							"department": category,
							"jobType": jobType,
							"postedAt": "",
							"state": "open",
						}
						jobs.append(job)
					jobIndex = jobIndex + 1
				groupIndex = groupIndex + 1
			await browser.close()
	except Exception as error:
		logger.exception("experlabs: fetchState failed: %s", error)
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
		logger.exception("experlabs: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("experlabs: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("experlabs: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("experlabs: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())