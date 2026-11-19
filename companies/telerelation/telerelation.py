import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("telerelation")

sourceUrl = "https://telerelation.com/careers"
baseUrl = "https://telerelation.com"
maxPages = 20
companyDir = Path(__file__).parent
snapshotPath = companyDir / "telerelation.json"


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
		logger.error("telerelation: %s not found. Title: %s. Preview: %s", selector, pageTitle, debugSnippet)
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
	marker = "job="
	hasMarker = marker in href
	if not hasMarker:
		return href
	tail = href.split(marker, 1)[1]
	stableId = tail.split("&")[0]
	return stableId


async def collectPage(page, jobs: list, seenIds: set) -> int:
	addedCount = 0
	cardLocator = page.locator("a.career-card")
	cardCount = await cardLocator.count()
	index = 0
	while index < cardCount:
		card = cardLocator.nth(index)
		hrefRaw = await card.get_attribute("href")
		href = normalizeText(hrefRaw)
		title = await firstText(card, ".career-card__title")
		stableId = extractStableId(href)
		isNew = stableId not in seenIds
		hasTitle = title != ""
		if hasTitle and isNew:
			seenIds.add(stableId)
			department = await firstText(card, ".career-card__badge")
			location = await nthText(card, ".career-card__meta-item span[title]", 0)
			jobType = await nthText(card, ".career-card__meta-item span[title]", 1)
			experience = await nthText(card, ".career-card__meta-item span[title]", 2)
			workMode = await firstText(card, ".career-card__chip")
			link = baseUrl + href
			extra = {"experience": experience, "workMode": workMode}
			job = buildJob(title, stableId, link, location, department, jobType, extra)
			jobs.append(job)
			addedCount = addedCount + 1
		index = index + 1
	return addedCount


async def goToNextPage(page) -> bool:
	paginationLinks = page.locator(".pagination a")
	linkCount = await paginationLinks.count()
	hasLinks = linkCount > 0
	if not hasLinks:
		return False
	nextLink = paginationLinks.last
	classAttr = await nextLink.get_attribute("class")
	hasClass = classAttr is not None
	if not hasClass:
		classAttr = ""
	isDisabled = "disabled" in classAttr
	if isDisabled:
		return False
	firstCard = page.locator("a.career-card").first
	previousHref = await firstCard.get_attribute("href")
	await nextLink.click()
	try:
		await page.wait_for_function("(previous) => { const el = document.querySelector('a.career-card'); return el !== null && el.getAttribute('href') !== previous; }", arg=previousHref, timeout=10000)
	except Exception as waitError:
		logger.warning("telerelation: page did not change after clicking next")
		return False
	return True


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=30000)
			await waitForCards(page, "a.career-card")
			seenIds = set()
			pageIndex = 0
			keepGoing = True
			while keepGoing and pageIndex < maxPages:
				addedCount = await collectPage(page, jobs, seenIds)
				noNewJobs = addedCount == 0
				if noNewJobs:
					keepGoing = False
				else:
					keepGoing = await goToNextPage(page)
				pageIndex = pageIndex + 1
			await browser.close()
	except Exception as error:
		logger.exception("telerelation: fetchState failed: %s", error)
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
		logger.exception("telerelation: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("telerelation: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("telerelation: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("telerelation: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())