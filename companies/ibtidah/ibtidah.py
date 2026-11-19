import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ibtidah")

sourceUrl = "https://portal.ibtidah.com/careers"
baseUrl = "https://portal.ibtidah.com"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "ibtidah.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def normalizeText(rawText) -> str:
	isNone = rawText is None
	if isNone:
		return ""
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


def stripLeadingBullet(rawText: str) -> str:
	normalized = normalizeText(rawText)
	hasBullet = normalized.startswith("•")
	if hasBullet:
		normalized = normalized[1:].strip()
	return normalized


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=30000)
			await page.wait_for_selector(".ibt-job-card", timeout=20000)
			cardLocator = page.locator(".ibt-job-card")
			cardCount = await cardLocator.count()
			index = 0
			while index < cardCount:
				currentCard = cardLocator.nth(index)
				stableId = await currentCard.get_attribute("id")
				hasStableId = stableId is not None
				if not hasStableId:
					stableId = ""
				titleLocator = currentCard.locator("h4.jobs-page")
				titleCount = await titleLocator.count()
				hasTitle = titleCount > 0
				if hasTitle:
					titleAttr = await titleLocator.first.get_attribute("title")
					hasTitleAttr = titleAttr is not None and titleAttr != ""
					if hasTitleAttr:
						title = normalizeText(titleAttr)
					else:
						titleText = await titleLocator.first.inner_text()
						title = normalizeText(titleText)
					hasNonEmptyTitle = title != ""
					if hasNonEmptyTitle:
						detailRowLocator = currentCard.locator(".text-14 .flex.align-items-center")
						detailRowCount = await detailRowLocator.count()
						hasLocationRow = detailRowCount >= 1
						if hasLocationRow:
							locationText = await detailRowLocator.nth(0).inner_text()
							location = normalizeText(locationText)
						else:
							location = ""
						hasDepartmentRow = detailRowCount >= 2
						if hasDepartmentRow:
							departmentText = await detailRowLocator.nth(1).inner_text()
							department = normalizeText(departmentText)
						else:
							department = ""
						jobTypeLocator = currentCard.locator(".full-time-badge")
						jobTypeCount = await jobTypeLocator.count()
						hasJobType = jobTypeCount > 0
						if hasJobType:
							jobTypeText = await jobTypeLocator.first.inner_text()
							jobType = stripLeadingBullet(jobTypeText)
						else:
							jobType = ""
						closesOnLocator = currentCard.locator("p:has-text('Closes on:') b")
						closesOnCount = await closesOnLocator.count()
						hasClosesOn = closesOnCount > 0
						if hasClosesOn:
							closesOnText = await closesOnLocator.first.inner_text()
							closesOn = normalizeText(closesOnText)
						else:
							closesOn = ""
						jobId = generateJobId(title, stableId)
						hasStableIdValue = stableId != ""
						if hasStableIdValue:
							link = baseUrl + "/" + stableId
						else:
							link = ""
						job = {
							"id": jobId,
							"title": title,
							"link": link,
							"location": location,
							"department": department,
							"jobType": jobType,
							"closesOn": closesOn,
							"postedAt": "",
							"state": "open",
						}
						jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("ibtidah: fetchState failed: %s", error)
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
		logger.exception("ibtidah: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("ibtidah: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("ibtidah: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("ibtidah: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())