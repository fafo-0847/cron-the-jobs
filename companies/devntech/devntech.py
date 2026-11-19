import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("devntech")

sourceUrl = "https://www.devntech.com/careers"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "devntech.json"


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


def normalizeText(rawText) -> str:
	isNone = rawText is None
	if isNone:
		return ""
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


def stripExperienceLabel(rawText: str) -> str:
	normalized = normalizeText(rawText)
	prefix = "Experience:"
	hasPrefix = normalized.startswith(prefix)
	if hasPrefix:
		normalized = normalized[len(prefix):].strip()
	return normalized


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=30000)
			await page.wait_for_selector("a[href*='.odoo.com/jobs/']", timeout=20000)
			applyLinkLocator = page.locator("a[href*='.odoo.com/jobs/']")
			applyLinkCount = await applyLinkLocator.count()
			index = 0
			while index < applyLinkCount:
				currentLink = applyLinkLocator.nth(index)
				href = await currentLink.get_attribute("href")
				hasHref = href is not None
				if not hasHref:
					href = ""
				cardLocator = currentLink.locator("xpath=ancestor::div[contains(@class,'bg-white')][1]")
				cardCount = await cardLocator.count()
				hasCard = cardCount > 0
				if hasCard:
					paragraphLocator = cardLocator.first.locator(".flex.flex-col p")
					paragraphCount = await paragraphLocator.count()
					hasTitle = paragraphCount >= 1
					if hasTitle:
						titleText = await paragraphLocator.nth(0).inner_text()
						title = normalizeText(titleText)
						hasNonEmptyTitle = title != ""
						if hasNonEmptyTitle:
							hasLocation = paragraphCount >= 2
							if hasLocation:
								locationText = await paragraphLocator.nth(1).inner_text()
								location = normalizeText(locationText)
							else:
								location = ""
							hasExperience = paragraphCount >= 3
							if hasExperience:
								experienceText = await paragraphLocator.nth(2).inner_text()
								experience = stripExperienceLabel(experienceText)
							else:
								experience = ""
							hasDescription = paragraphCount >= 4
							if hasDescription:
								descriptionText = await paragraphLocator.nth(3).inner_text()
								description = normalizeText(descriptionText)
							else:
								description = ""
							stableId = extractStableId(href)
							jobId = generateJobId(title, stableId)
							job = {
								"id": jobId,
								"title": title,
								"link": href,
								"location": location,
								"department": "",
								"jobType": "",
								"experience": experience,
								"description": description,
								"postedAt": "",
								"state": "open",
							}
							jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("devntech: fetchState failed: %s", error)
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
		logger.exception("devntech: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("devntech: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("devntech: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("devntech: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())