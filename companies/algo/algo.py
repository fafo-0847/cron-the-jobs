import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("algo")

sourceUrl = "https://www.algo.com/careers/#open-positions"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "algo.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def extractStableId(elementId: str) -> str:
	prefix = "bhrPositionID_"
	hasPrefix = elementId.startswith(prefix)
	if hasPrefix:
		stableId = elementId[len(prefix):]
	else:
		stableId = ""
	return stableId


def normalizeText(rawText: str) -> str:
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


def normalizeLink(href: str) -> str:
	isProtocolRelative = href.startswith("//")
	if isProtocolRelative:
		link = "https:" + href
	else:
		link = href
	return link


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=30000)
			await page.wait_for_selector(".BambooHR-ATS-Jobs-Item", timeout=20000)
			departmentLocator = page.locator(".BambooHR-ATS-Department-Item")
			departmentCount = await departmentLocator.count()
			departmentIndex = 0
			while departmentIndex < departmentCount:
				currentDepartment = departmentLocator.nth(departmentIndex)
				headerLocator = currentDepartment.locator(".BambooHR-ATS-Department-Header")
				headerCount = await headerLocator.count()
				hasHeader = headerCount > 0
				if hasHeader:
					headerText = await headerLocator.first.inner_text()
					department = normalizeText(headerText)
				else:
					department = ""
				jobItemLocator = currentDepartment.locator(".BambooHR-ATS-Jobs-Item")
				jobItemCount = await jobItemLocator.count()
				jobIndex = 0
				while jobIndex < jobItemCount:
					currentJobItem = jobItemLocator.nth(jobIndex)
					elementId = await currentJobItem.get_attribute("id")
					hasElementId = elementId is not None
					if not hasElementId:
						elementId = ""
					linkLocator = currentJobItem.locator("a")
					linkCount = await linkLocator.count()
					hasLink = linkCount > 0
					if hasLink:
						titleText = await linkLocator.first.inner_text()
						title = normalizeText(titleText)
						href = await linkLocator.first.get_attribute("href")
						hasHref = href is not None
						if not hasHref:
							href = ""
						link = normalizeLink(href)
						locationLocator = currentJobItem.locator(".BambooHR-ATS-Location")
						locationCount = await locationLocator.count()
						hasLocation = locationCount > 0
						if hasLocation:
							locationText = await locationLocator.first.inner_text()
							location = normalizeText(locationText)
						else:
							location = ""
						stableId = extractStableId(elementId)
						jobId = generateJobId(title, stableId)
						job = {
							"id": jobId,
							"title": title,
							"link": link,
							"location": location,
							"department": department,
							"jobType": "",
							"postedAt": "",
							"state": "open",
						}
						jobs.append(job)
					jobIndex = jobIndex + 1
				departmentIndex = departmentIndex + 1
			await browser.close()
	except Exception as error:
		logger.exception("algo: fetchState failed: %s", error)
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
		logger.exception("algo: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("algo: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("algo: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("algo: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())