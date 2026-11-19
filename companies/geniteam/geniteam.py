import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("geniteam")

sourceUrl = "https://geniteam-careers.web.app"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "geniteam.json"


def generateJobId(title: str, experience: str) -> str:
	raw = title + "|" + experience
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
			await page.wait_for_selector(".v-card.rounded-card", timeout=20000)
			cardLocator = page.locator(".v-card.rounded-card")
			cardCount = await cardLocator.count()
			index = 0
			while index < cardCount:
				currentCard = cardLocator.nth(index)
				titleLocator = currentCard.locator(".headline")
				titleCount = await titleLocator.count()
				hasTitle = titleCount > 0
				if hasTitle:
					titleText = await titleLocator.first.inner_text()
					title = normalizeText(titleText)
					experienceLocator = currentCard.locator(".grey--text")
					experienceCount = await experienceLocator.count()
					hasExperience = experienceCount > 0
					if hasExperience:
						experienceText = await experienceLocator.first.inner_text()
						experience = normalizeText(experienceText)
					else:
						experience = ""
					descriptionLocator = currentCard.locator(".v-card__text")
					descriptionCount = await descriptionLocator.count()
					hasDescription = descriptionCount > 0
					if hasDescription:
						descriptionText = await descriptionLocator.first.inner_text()
						description = normalizeText(descriptionText)
					else:
						description = ""
					applyLinkLocator = currentCard.locator("a[href^='mailto:']")
					applyLinkCount = await applyLinkLocator.count()
					hasApplyLink = applyLinkCount > 0
					if hasApplyLink:
						applyLink = await applyLinkLocator.first.get_attribute("href")
						hasApplyLinkValue = applyLink is not None
						if not hasApplyLinkValue:
							applyLink = ""
					else:
						applyLink = ""
					jobId = generateJobId(title, experience)
					job = {
						"id": jobId,
						"title": title,
						"link": applyLink,
						"location": "",
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
		logger.exception("geniteam: fetchState failed: %s", error)
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
		logger.exception("geniteam: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("geniteam: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("geniteam: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("geniteam: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())