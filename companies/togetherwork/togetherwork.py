import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("togetherwork")

sourceUrl = "https://www.togetherwork.com/jobs/togetherwork/"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "togetherwork.json"


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


# Nov 2026: /jobs/ now 404s. Listings moved to the WordPress archive /jobs/togetherwork/
# (article.post > h2.entry-title > a, 10 per page, /page/N/ pagination). The site serves a
# bot-check stub to plain HTTP clients, so this still uses a real browser.
maxPages = 10
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def buildPageUrl(url: str, pageNumber: int) -> str:
	baseUrl = url.rstrip("/") + "/"
	return baseUrl if pageNumber == 1 else f"{baseUrl}page/{pageNumber}/"


async def parseArchivePage(page) -> list[dict[str, Any]]:
	jobs = []
	articleLocator = page.locator("article.post")
	articleCount = await articleLocator.count()
	for index in range(articleCount):
		article = articleLocator.nth(index)
		titleLinkLocator = article.locator("h2.entry-title a")
		if await titleLinkLocator.count() == 0:
			continue
		title = normalizeText(await titleLinkLocator.first.inner_text())
		href = await titleLinkLocator.first.get_attribute("href") or ""
		if title == "" or "/jobs/" not in href:
			continue
		summaryLocator = article.locator("p")
		description = normalizeText(await summaryLocator.first.inner_text()) if await summaryLocator.count() > 0 else ""
		jobs.append({
			"id": generateJobId(title, extractStableId(href)),
			"title": title,
			"link": href,
			"location": "",
			"department": "",
			"jobType": "",
			"description": description,
			"postedAt": "",
			"state": "open",
		})
	return jobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page(user_agent=userAgent)
			seenLinks: set[str] = set()
			for pageNumber in range(1, maxPages + 1):
				response = await page.goto(buildPageUrl(url, pageNumber), wait_until="domcontentloaded", timeout=30000)
				isMissingPage = response is not None and response.status == 404
				if isMissingPage and pageNumber > 1:
					break
				await page.wait_for_selector("article.post h2.entry-title a", timeout=20000)
				pageJobs = [job for job in await parseArchivePage(page) if job["link"] not in seenLinks]
				if len(pageJobs) == 0:
					break
				for job in pageJobs:
					seenLinks.add(job["link"])
					jobs.append(job)
				hasNextPage = await page.locator(f"a[href*='/page/{pageNumber + 1}/']").count() > 0
				if not hasNextPage:
					break
			await browser.close()
	except Exception as error:
		logger.exception("togetherwork: fetchState failed: %s", error)
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
		logger.exception("togetherwork: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("togetherwork: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("togetherwork: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("togetherwork: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())