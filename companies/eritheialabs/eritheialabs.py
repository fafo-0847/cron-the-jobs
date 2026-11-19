import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("eritheialabs")

sourceUrl = "https://www.eritheialabs.com/careers"
baseUrl = "https://www.eritheialabs.com"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "eritheialabs.json"


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


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=30000)
			await page.wait_for_selector("tbody#accordion tr[role='button']", timeout=20000)
			rowLocator = page.locator("tbody#accordion tr[role='button']")
			rowCount = await rowLocator.count()
			index = 0
			while index < rowCount:
				currentRow = rowLocator.nth(index)
				cellLocator = currentRow.locator("td")
				cellCount = await cellLocator.count()
				hasEnoughCells = cellCount >= 4
				if hasEnoughCells:
					jobCodeText = await cellLocator.nth(0).inner_text()
					titleText = await cellLocator.nth(1).inner_text()
					locationText = await cellLocator.nth(2).inner_text()
					departmentText = await cellLocator.nth(3).inner_text()
					jobCode = normalizeText(jobCodeText)
					title = normalizeText(titleText)
					location = normalizeText(locationText)
					department = normalizeText(departmentText)
					closesAt = ""
					hasClosedColumn = cellCount >= 5
					if hasClosedColumn:
						closedText = await cellLocator.nth(4).inner_text()
						closesAt = normalizeText(closedText)
					collapseTarget = await currentRow.get_attribute("href")
					hasCollapseTarget = collapseTarget is not None
					link = ""
					if hasCollapseTarget:
						collapseLocator = page.locator(collapseTarget)
						applyLinkLocator = collapseLocator.locator("a.ot-btn")
						applyLinkCount = await applyLinkLocator.count()
						hasApplyLink = applyLinkCount > 0
						if hasApplyLink:
							applyHref = await applyLinkLocator.first.get_attribute("href")
							hasApplyHref = applyHref is not None
							if hasApplyHref:
								link = baseUrl + applyHref
					jobId = generateJobId(title, jobCode)
					job = {
						"id": jobId,
						"title": title,
						"link": link,
						"location": location,
						"department": department,
						"jobType": "",
						"jobCode": jobCode,
						"closesAt": closesAt,
						"postedAt": "",
						"state": "open",
					}
					jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("eritheialabs: fetchState failed: %s", error)
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
		logger.exception("eritheialabs: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("eritheialabs: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("eritheialabs: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("eritheialabs: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())