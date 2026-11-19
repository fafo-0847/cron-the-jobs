import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("postex")

sourceUrl = "https://www.postex.com/en/careers/#vacancies"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "postex.json"


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


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=30000)
			await page.wait_for_selector(".jobs-list li", timeout=20000)
			itemLocator = page.locator(".jobs-list li")
			itemCount = await itemLocator.count()
			index = 0
			while index < itemCount:
				currentItem = itemLocator.nth(index)
				titleLocator = currentItem.locator("h3")
				titleCount = await titleLocator.count()
				hasTitle = titleCount > 0
				if hasTitle:
					titleText = await titleLocator.first.inner_text()
					title = normalizeText(titleText)
					hasNonEmptyTitle = title != ""
					if hasNonEmptyTitle:
						linkLocator = currentItem.locator("a")
						linkCount = await linkLocator.count()
						hasLink = linkCount > 0
						if hasLink:
							href = await linkLocator.first.get_attribute("href")
							hasHref = href is not None
							if not hasHref:
								href = ""
						else:
							href = ""
						detailLocator = currentItem.locator(".job-detail li")
						detailCount = await detailLocator.count()
						detailValues = []
						detailIndex = 0
						while detailIndex < detailCount:
							detailText = await detailLocator.nth(detailIndex).inner_text()
							detailValue = normalizeText(detailText)
							detailValues.append(detailValue)
							detailIndex = detailIndex + 1
						hasLocationDetail = len(detailValues) >= 1
						if hasLocationDetail:
							location = detailValues[0]
						else:
							location = ""
						hasEducationDetail = len(detailValues) >= 2
						if hasEducationDetail:
							education = detailValues[1]
						else:
							education = ""
						hasJobTypeDetail = len(detailValues) >= 3
						if hasJobTypeDetail:
							jobType = detailValues[2]
						else:
							jobType = ""
						closingTagLocator = currentItem.locator(".closing-tag")
						closingTagCount = await closingTagLocator.count()
						hasClosingTag = closingTagCount > 0
						if hasClosingTag:
							closingTagText = await closingTagLocator.first.inner_text()
							closingStatus = normalizeText(closingTagText)
						else:
							closingStatus = ""
						stableId = extractStableId(href)
						jobId = generateJobId(title, stableId)
						job = {
							"id": jobId,
							"title": title,
							"link": href,
							"location": location,
							"department": "",
							"jobType": jobType,
							"education": education,
							"closingStatus": closingStatus,
							"postedAt": "",
							"state": "open",
						}
						jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("postex: fetchState failed: %s", error)
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
		logger.exception("postex: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("postex: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("postex: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("postex: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())