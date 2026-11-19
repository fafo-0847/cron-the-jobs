import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("phaedrasolutions")

sourceUrl = "https://www.phaedrasolutions.com/company/careers"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "phaedrasolutions.json"


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
			await page.wait_for_selector(".career-card", timeout=20000)
			groupLocator = page.locator(".career-card-block")
			groupCount = await groupLocator.count()
			groupIndex = 0
			while groupIndex < groupCount:
				currentGroup = groupLocator.nth(groupIndex)
				departmentLocator = currentGroup.locator(".heading-97")
				departmentCount = await departmentLocator.count()
				hasDepartment = departmentCount > 0
				if hasDepartment:
					departmentText = await departmentLocator.first.inner_text()
					department = normalizeText(departmentText)
				else:
					department = ""
				jobCardLocator = currentGroup.locator(".career-card")
				jobCardCount = await jobCardLocator.count()
				jobIndex = 0
				while jobIndex < jobCardCount:
					currentJobCard = jobCardLocator.nth(jobIndex)
					titleLocator = currentJobCard.locator(".career-card-text")
					titleCount = await titleLocator.count()
					hasTitle = titleCount > 0
					if hasTitle:
						titleText = await titleLocator.first.inner_text()
						title = normalizeText(titleText)
						hasNonEmptyTitle = title != ""
						if hasNonEmptyTitle:
							metaLocator = currentJobCard.locator(".div-block-106 > div")
							metaCount = await metaLocator.count()
							hasLocation = metaCount >= 1
							if hasLocation:
								locationText = await metaLocator.nth(0).inner_text()
								location = normalizeText(locationText)
							else:
								location = ""
							hasExperience = metaCount >= 2
							if hasExperience:
								experienceText = await metaLocator.nth(1).inner_text()
								experience = normalizeText(experienceText)
							else:
								experience = ""
							applyLinkLocator = currentJobCard.locator("a.inner-btn")
							applyLinkCount = await applyLinkLocator.count()
							hasApplyLink = applyLinkCount > 0
							if hasApplyLink:
								href = await applyLinkLocator.first.get_attribute("href")
								hasHref = href is not None
								if not hasHref:
									href = ""
							else:
								href = ""
							stableId = extractStableId(href)
							jobId = generateJobId(title, stableId)
							job = {
								"id": jobId,
								"title": title,
								"link": href,
								"location": location,
								"department": department,
								"jobType": "",
								"experience": experience,
								"postedAt": "",
								"state": "open",
							}
							jobs.append(job)
					jobIndex = jobIndex + 1
				groupIndex = groupIndex + 1
			await browser.close()
	except Exception as error:
		logger.exception("phaedrasolutions: fetchState failed: %s", error)
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
		logger.exception("phaedrasolutions: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("phaedrasolutions: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("phaedrasolutions: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("phaedrasolutions: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())