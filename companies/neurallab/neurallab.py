import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("neurallab")

sourceUrl = "https://neurallab.co/careers"
baseUrl = "https://neurallab.co"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "neurallab.json"


def generateJobId(title: str, jobType: str, location: str) -> str:
	raw = title + "|" + jobType + "|" + location
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


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
			await page.goto(baseUrl, wait_until="domcontentloaded", timeout=30000)
			careersLinkLocator = page.locator("a[href*='career' i]")
			careersLinkCount = await careersLinkLocator.count()
			hasCareersLink = careersLinkCount > 0
			if hasCareersLink:
				await careersLinkLocator.first.click()
			else:
				logger.warning("neurallab: no careers link found on homepage, falling back to direct navigation")
				await page.goto(url, wait_until="domcontentloaded", timeout=30000)
			try:
				await page.wait_for_selector("[class*='Careers_jobCard__']", timeout=30000)
			except Exception as timeoutError:
				pageContent = await page.content()
				debugSnippet = pageContent[:3000]
				logger.error("neurallab: job card selector not found. Page content preview: %s", debugSnippet)
				pageTitle = await page.title()
				logger.error("neurallab: page title was: %s", pageTitle)
				raise
			cardLocator = page.locator("[class*='Careers_jobCard__']")
			cardCount = await cardLocator.count()
			index = 0
			while index < cardCount:
				currentCard = cardLocator.nth(index)
				titleLocator = currentCard.locator("[class*='Careers_jobTitle__']")
				titleCount = await titleLocator.count()
				hasTitle = titleCount > 0
				if hasTitle:
					titleText = await titleLocator.first.inner_text()
					title = normalizeText(titleText)
					hasNonEmptyTitle = title != ""
					if hasNonEmptyTitle:
						categoryLocator = currentCard.locator("[class*='Careers_jobCategory__']")
						categoryCount = await categoryLocator.count()
						hasCategory = categoryCount > 0
						if hasCategory:
							categoryText = await categoryLocator.first.inner_text()
							department = normalizeText(categoryText)
						else:
							department = ""
						jobTypeLocator = currentCard.locator("[class*='Careers_jobType__']")
						jobTypeCount = await jobTypeLocator.count()
						hasJobType = jobTypeCount > 0
						if hasJobType:
							jobTypeText = await jobTypeLocator.first.inner_text()
							jobType = normalizeText(jobTypeText)
						else:
							jobType = ""
						locationLocator = currentCard.locator("[class*='Careers_jobLocation__']")
						locationCount = await locationLocator.count()
						hasLocation = locationCount > 0
						if hasLocation:
							locationText = await locationLocator.first.inner_text()
							location = normalizeText(locationText)
						else:
							location = ""
						workModeLocator = currentCard.locator("[class*='Careers_workModeValue__']")
						workModeCount = await workModeLocator.count()
						hasWorkMode = workModeCount > 0
						if hasWorkMode:
							workModeText = await workModeLocator.first.inner_text()
							workMode = normalizeText(workModeText)
						else:
							workMode = ""
						descriptionLocator = currentCard.locator("[class*='Careers_jobDescription__']")
						descriptionCount = await descriptionLocator.count()
						hasDescription = descriptionCount > 0
						if hasDescription:
							descriptionText = await descriptionLocator.first.inner_text()
							description = normalizeText(descriptionText)
						else:
							description = ""
						applyLinkLocator = currentCard.locator("[class*='Careers_applyBtn__']")
						applyLinkCount = await applyLinkLocator.count()
						hasApplyLink = applyLinkCount > 0
						if hasApplyLink:
							href = await applyLinkLocator.first.get_attribute("href")
							hasHref = href is not None
							if not hasHref:
								href = ""
						else:
							href = ""
						jobId = generateJobId(title, jobType, location)
						link = baseUrl + href
						job = {
							"id": jobId,
							"title": title,
							"link": link,
							"location": location,
							"department": department,
							"jobType": jobType,
							"workMode": workMode,
							"description": description,
							"postedAt": "",
							"state": "open",
						}
						jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("neurallab: fetchState failed: %s", error)
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
		logger.exception("neurallab: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("neurallab: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("neurallab: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("neurallab: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())