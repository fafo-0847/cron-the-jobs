import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from companies._shared import browser as sharedBrowser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("qbatch")

sourceUrl = "https://careers.qbatch.com/jobs"
baseUrl = "https://careers.qbatch.com"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "qbatch.json"


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


def normalizeText(rawText: str) -> str:
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


def normalizeCategory(rawText: str) -> str:
	normalized = normalizeText(rawText)
	parts = normalized.split("-")
	category = parts[0].strip()
	return category


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await sharedBrowser.newPage(browser)
			await sharedBrowser.gotoChecked(page, url, waitUntil="domcontentloaded", timeoutMs=30000)
			await page.wait_for_selector("ul.job-list li.heading", timeout=20000)
			groupLocator = page.locator("ul.open-list > li")
			groupCount = await groupLocator.count()
			groupIndex = 0
			while groupIndex < groupCount:
				currentGroup = groupLocator.nth(groupIndex)
				headingLocator = currentGroup.locator(".role-title h5")
				headingCount = await headingLocator.count()
				hasHeading = headingCount > 0
				if hasHeading:
					headingText = await headingLocator.first.inner_text()
					department = normalizeCategory(headingText)
				else:
					department = ""
				jobItemLocator = currentGroup.locator("ul.job-list li.heading")
				jobItemCount = await jobItemLocator.count()
				jobIndex = 0
				while jobIndex < jobItemCount:
					currentJobItem = jobItemLocator.nth(jobIndex)
					titleLocator = currentJobItem.locator("a.job-title")
					titleCount = await titleLocator.count()
					hasTitle = titleCount > 0
					if hasTitle:
						titleText = await titleLocator.first.inner_text()
						title = normalizeText(titleText)
						href = await titleLocator.first.get_attribute("href")
						hasHref = href is not None
						if not hasHref:
							href = ""
						locationInfoLocator = currentJobItem.locator("a.location-info")
						locationInfoCount = await locationInfoLocator.count()
						hasLocationInfo = locationInfoCount > 0
						if hasLocationInfo:
							locationInfoText = await locationInfoLocator.first.inner_text()
							locationLines = locationInfoText.split("\n")
							hasLocationLine = len(locationLines) >= 1
							if hasLocationLine:
								location = normalizeText(locationLines[0])
							else:
								location = ""
							hasJobTypeLine = len(locationLines) >= 2
							if hasJobTypeLine:
								jobType = normalizeText(locationLines[1])
							else:
								jobType = ""
						else:
							location = ""
							jobType = ""
						descLocator = currentJobItem.locator("a.job-desc")
						descCount = await descLocator.count()
						hasDesc = descCount > 0
						if hasDesc:
							descText = await descLocator.first.inner_text()
							description = normalizeText(descText)
						else:
							description = ""
						stableId = extractStableId(href)
						jobId = generateJobId(title, stableId)
						link = baseUrl + href
						job = {
							"id": jobId,
							"title": title,
							"link": link,
							"location": location,
							"department": department,
							"jobType": jobType,
							"description": description,
							"postedAt": "",
							"state": "open",
						}
						jobs.append(job)
					jobIndex = jobIndex + 1
				groupIndex = groupIndex + 1
			await browser.close()
	except Exception as error:
		logger.exception("qbatch: fetchState failed: %s", error)
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
		logger.exception("qbatch: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("qbatch: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("qbatch: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("qbatch: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())