import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from companies._shared import browser as sharedBrowser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mergestack")

sourceUrl = "https://www.mergestack.com/career"
baseUrl = "https://www.mergestack.com"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "mergestack.json"


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


def buildJob(title: str, stableId: str, link: str, location: str, department: str, jobType: str, extra: dict) -> dict:
	jobId = generateJobId(title, stableId)
	job = {
		"id": jobId,
		"title": title,
		"link": link,
		"location": location,
		"department": department,
		"jobType": jobType,
		"postedAt": "",
		"state": "open",
	}
	job.update(extra)
	return job


async def waitForCards(page, selector: str) -> None:
	try:
		await page.wait_for_selector(selector, timeout=20000)
	except Exception as timeoutError:
		pageContent = await page.content()
		debugSnippet = pageContent[:3000]
		pageTitle = await page.title()
		logger.error("mergestack: %s not found. Title: %s. Preview: %s", selector, pageTitle, debugSnippet)
		raise


async def firstText(parent, selector: str) -> str:
	locator = parent.locator(selector)
	count = await locator.count()
	hasMatch = count > 0
	if not hasMatch:
		return ""
	rawText = await locator.first.inner_text()
	text = normalizeText(rawText)
	return text


async def firstAttr(parent, selector: str, attribute: str) -> str:
	locator = parent.locator(selector)
	count = await locator.count()
	hasMatch = count > 0
	if not hasMatch:
		return ""
	rawValue = await locator.first.get_attribute(attribute)
	value = normalizeText(rawValue)
	return value


async def nthText(parent, selector: str, position: int) -> str:
	locator = parent.locator(selector)
	count = await locator.count()
	hasPosition = count > position
	if not hasPosition:
		return ""
	rawText = await locator.nth(position).inner_text()
	text = normalizeText(rawText)
	return text


async def allTexts(parent, selector: str) -> list:
	values = []
	locator = parent.locator(selector)
	count = await locator.count()
	index = 0
	while index < count:
		rawText = await locator.nth(index).inner_text()
		text = normalizeText(rawText)
		values.append(text)
		index = index + 1
	return values


def extractStableId(href: str) -> str:
	segments = href.strip("/").split("/")
	stableId = segments[-1]
	return stableId


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await sharedBrowser.newPage(browser)
			await sharedBrowser.gotoChecked(page, url, waitUntil="domcontentloaded", timeoutMs=30000)
			await waitForCards(page, "a.job-row")
			cardLocator = page.locator("a.job-row")
			cardCount = await cardLocator.count()
			index = 0
			while index < cardCount:
				card = cardLocator.nth(index)
				hrefRaw = await card.get_attribute("href")
				href = normalizeText(hrefRaw)
				title = await firstText(card, ".job-row__title")
				location = await nthText(card, ".job-row__meta .tag", 0)
				experience = await nthText(card, ".job-row__meta .tag", 1)
				status = await nthText(card, ".job-row__meta .tag", 2)
				statusLower = status.lower()
				isClosed = statusLower in ["closed", "inactive", "filled"]
				hasTitle = title != ""
				if hasTitle and not isClosed:
					stableId = extractStableId(href)
					link = baseUrl + href
					extra = {"experience": experience, "status": status}
					job = buildJob(title, stableId, link, location, "", "", extra)
					jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("mergestack: fetchState failed: %s", error)
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
		logger.exception("mergestack: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("mergestack: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("mergestack: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("mergestack: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())