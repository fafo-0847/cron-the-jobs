import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("automotive")

sourceUrl = "https://www.automotive-ai.com/jobs"
baseUrl = "https://www.automotive-ai.com"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "automotive.json"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def extractStableId(href: str) -> str:
	slug = href.strip("/").split("/")[-1]
	tokens = slug.split("-")
	hasTokens = len(tokens) > 0
	if hasTokens:
		lastToken = tokens[-1]
	else:
		lastToken = ""
	isNumeric = lastToken.isdigit()
	if isNumeric:
		stableId = lastToken
	else:
		stableId = slug
	return stableId


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
			await page.wait_for_selector("#jobs_grid .card", timeout=20000)
			cardLocator = page.locator("#jobs_grid .card")
			cardCount = await cardLocator.count()
			index = 0
			while index < cardCount:
				currentCard = cardLocator.nth(index)
				anchorLocator = currentCard.locator("a")
				anchorCount = await anchorLocator.count()
				hasAnchor = anchorCount > 0
				if hasAnchor:
					href = await anchorLocator.first.get_attribute("href")
					hasHref = href is not None
					if not hasHref:
						href = ""
					titleLocator = currentCard.locator("h3")
					titleCount = await titleLocator.count()
					hasTitle = titleCount > 0
					if hasTitle:
						titleText = await titleLocator.first.inner_text()
						title = normalizeText(titleText)
						localityLocator = currentCard.locator("[itemprop='addressLocality']")
						localityCount = await localityLocator.count()
						hasLocality = localityCount > 0
						if hasLocality:
							localityText = await localityLocator.first.inner_text()
							locality = normalizeText(localityText)
						else:
							locality = ""
						countryLocator = currentCard.locator("[itemprop='addressCountry']")
						countryCount = await countryLocator.count()
						hasCountry = countryCount > 0
						if hasCountry:
							countryText = await countryLocator.first.inner_text()
							country = normalizeText(countryText)
						else:
							country = ""
						locationParts = []
						hasLocalityText = locality != ""
						if hasLocalityText:
							locationParts.append(locality)
						hasCountryText = country != ""
						if hasCountryText:
							locationParts.append(country)
						location = ", ".join(locationParts)
						departmentLocator = currentCard.locator(".fa-sitemap")
						departmentCount = await departmentLocator.count()
						hasDepartment = departmentCount > 0
						if hasDepartment:
							departmentContainer = departmentLocator.first.locator("xpath=..")
							departmentSpanLocator = departmentContainer.locator("span")
							departmentSpanCount = await departmentSpanLocator.count()
							hasDepartmentSpan = departmentSpanCount > 0
							if hasDepartmentSpan:
								departmentText = await departmentSpanLocator.first.inner_text()
								department = normalizeText(departmentText)
							else:
								department = ""
						else:
							department = ""
						jobTypeLocator = currentCard.locator(".fa-suitcase")
						jobTypeCount = await jobTypeLocator.count()
						hasJobType = jobTypeCount > 0
						if hasJobType:
							jobTypeContainer = jobTypeLocator.first.locator("xpath=..")
							jobTypeSpanLocator = jobTypeContainer.locator("span")
							jobTypeSpanCount = await jobTypeSpanLocator.count()
							hasJobTypeSpan = jobTypeSpanCount > 0
							if hasJobTypeSpan:
								jobTypeText = await jobTypeSpanLocator.first.inner_text()
								jobType = normalizeText(jobTypeText)
							else:
								jobType = ""
						else:
							jobType = ""
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
							"postedAt": "",
							"state": "open",
						}
						jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("automotive: fetchState failed: %s", error)
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
		logger.exception("automotive: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("automotive: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("automotive: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("automotive: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())