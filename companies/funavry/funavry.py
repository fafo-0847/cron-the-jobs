import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("funavry")

sourceUrl = "https://www.funavry.com/career.html"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "funavry.json"


def generateJobId(title: str, location: str, jobType: str) -> str:
	raw = title + "|" + location + "|" + jobType
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def parseDetailLine(text: str) -> dict[str, str]:
	details = {}
	normalized = text.replace("\xa0", " ").strip()
	parts = normalized.split("|")
	index = 0
	while index < len(parts):
		chunk = parts[index].strip()
		hasColon = ":" in chunk
		if hasColon:
			key, value = chunk.split(":", 1)
			details[key.strip().lower()] = value.strip()
		index = index + 1
	return details


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=30000)
			await page.wait_for_selector("#v-pills-tab a.nav-link", timeout=20000)
			navLinkLocator = page.locator("#v-pills-tab a.nav-link")
			navLinkCount = await navLinkLocator.count()
			index = 0
			while index < navLinkCount:
				currentLink = navLinkLocator.nth(index)
				headingLocator = currentLink.locator("h3")
				paragraphLocator = currentLink.locator("p")
				headingCount = await headingLocator.count()
				paragraphCount = await paragraphLocator.count()
				hasHeading = headingCount > 0
				hasParagraph = paragraphCount > 0
				if hasHeading and hasParagraph:
					headingText = await headingLocator.first.inner_text()
					paragraphText = await paragraphLocator.first.inner_text()
					title = headingText.replace("\xa0", " ").strip()
					details = parseDetailLine(paragraphText)
					location = details.get("location", "")
					jobType = details.get("job type", "")
					experience = details.get("experience", "")
					jobShift = details.get("job shift", "")
					jobId = generateJobId(title, location, jobType)
					job = {
						"id": jobId,
						"title": title,
						"link": url,
						"location": location,
						"department": "",
						"jobType": jobType,
						"experience": experience,
						"jobShift": jobShift,
						"postedAt": "",
						"state": "open",
					}
					jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("funavry: fetchState failed: %s", error)
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
		logger.exception("funavry: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("funavry: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("funavry: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("funavry: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())