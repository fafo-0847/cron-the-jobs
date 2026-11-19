import datetime
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("venturedive")

sourceUrl = "https://venturedive.applytojob.com/apply/#alljobs"
snapshotPath = Path(__file__).parent / "venturedive.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def loadExistingSnapshot() -> dict[str, Any]:
	snapshotExists = snapshotPath.exists()
	if snapshotExists:
		fileContent = snapshotPath.read_text(encoding="utf-8")
		existingSnapshot = json.loads(fileContent)
	else:
		existingSnapshot = dict(sourceUrl=sourceUrl, fetchedAt="", state="unknown", jobs=[])
	return existingSnapshot


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	errorOccurred = False
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=45000)
			await page.wait_for_selector("table.resumator-job-listings", timeout=30000)
			await page.wait_for_timeout(2000)
			rowElements = await page.query_selector_all("table.resumator-job-listings tr")
			currentDepartment = ""
			rowIndex = 0
			rowCount = len(rowElements)
			while rowIndex < rowCount:
				row = rowElements[rowIndex]
				rowClass = await row.get_attribute("class")
				rowClass = rowClass if rowClass is not None else ""
				isDepartmentHeadingRow = "resumator-table-heading-row" in rowClass
				isJobRow = "resumator-table-row" in rowClass
				if isDepartmentHeadingRow:
					currentDepartment = await extractDepartmentName(row)
				elif isJobRow:
					job = await parseRow(row, currentDepartment)
					jobFound = job is not None
					if jobFound:
						jobs.append(job)
				rowIndex = rowIndex + 1
			await browser.close()
	except Exception as fetchException:
		errorOccurred = True
		logger.exception("Failed to fetch venturedive jobs: %s", fetchException)
	stateResult = "error" if errorOccurred else "open"
	state = dict(jobs=jobs, state=stateResult)
	return state


async def extractDepartmentName(row) -> str:
	departmentName = ""
	try:
		departmentElement = await row.query_selector("span.resumator-department-name")
		departmentElementExists = departmentElement is not None
		if departmentElementExists:
			rawDepartmentName = await departmentElement.inner_text()
			departmentName = normalizeText(rawDepartmentName)
	except Exception as departmentException:
		logger.exception("Failed to extract department name: %s", departmentException)
	return departmentName


async def parseRow(row, currentDepartment: str) -> dict[str, Any]:
	parsedJob = None
	try:
		linkElement = await row.query_selector("a.resumator-job-title-link")
		linkElementExists = linkElement is not None
		if not linkElementExists:
			return parsedJob
		rawTitle = await linkElement.inner_text()
		title = normalizeText(rawTitle)
		link = await linkElement.get_attribute("href")
		stableId = extractStableId(link)
		locationElement = await row.query_selector("td.resumator-job-location-column")
		locationElementExists = locationElement is not None
		if locationElementExists:
			rawLocation = await locationElement.inner_text()
			location = normalizeText(rawLocation)
		else:
			location = ""
		jobId = generateJobId(title, stableId)
		parsedJob = dict(
			id=jobId,
			title=title,
			link=link,
			location=location,
			department=currentDepartment,
			jobType="",
			postedAt="",
			state="open",
		)
	except Exception as parseException:
		logger.exception("Failed to parse venturedive row: %s", parseException)
	return parsedJob


def extractStableId(link: str) -> str:
	linkIsEmpty = link is None or link == ""
	if linkIsEmpty:
		return ""
	matchResult = re.search(r"/apply/([A-Za-z0-9]+)/", link)
	matchFound = matchResult is not None
	if matchFound:
		stableId = matchResult.group(1)
	else:
		stableId = ""
	return stableId


def normalizeText(text: str) -> str:
	normalized = text.replace("\xa0", " ").strip()
	normalized = " ".join(normalized.split())
	return normalized


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	newJobs = state.get("jobs", [])
	oldJobs = existingSnapshot.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("Suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
		return dict(existingSnapshot)
	fetchedAt = datetime.datetime.now(datetime.timezone.utc).isoformat()
	snapshot = dict(
		sourceUrl=sourceUrl,
		fetchedAt=fetchedAt,
		state=state.get("state", "unknown"),
		jobs=newJobs,
	)
	return snapshot


def writeSnapshot(snapshot: dict) -> None:
	snapshotJson = json.dumps(snapshot, indent=2)
	snapshotPath.write_text(snapshotJson, encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("venturedive: wrote %d jobs", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())