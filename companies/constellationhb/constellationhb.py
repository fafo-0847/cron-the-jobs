import hashlib
import json
import logging
import datetime
import re
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("constellationhb")

sourceUrl = "https://www.constellationhb.com/careers/"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "constellationhb.json"


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


def extractStableId(href: str, panelSlug: str) -> str:
	isWorkday = "myworkdayjobs.com" in href
	if isWorkday:
		match = re.search(r"_R(\d+)", href)
		hasMatch = match is not None
		if hasMatch:
			return "workday-" + match.group(1)
	isLinkedIn = "linkedin.com/jobs/view/" in href
	if isLinkedIn:
		match = re.search(r"/jobs/view/(\d+)", href)
		hasMatch = match is not None
		if hasMatch:
			return "linkedin-" + match.group(1)
	hasPanelSlug = panelSlug != ""
	if hasPanelSlug:
		return "slug-" + panelSlug
	return ""


def parseJobSpecs(rawText: str) -> tuple:
	normalized = normalizeText(rawText)
	hasTypeMarker = "Type:" in normalized
	if hasTypeMarker:
		parts = normalized.split("Type:", 1)
		locationPart = parts[0]
		jobTypePart = parts[1]
	else:
		locationPart = normalized
		jobTypePart = ""
	locationPart = locationPart.replace("Location:", "").strip()
	jobTypePart = jobTypePart.strip()
	return locationPart, jobTypePart


def stripLabel(rawText: str) -> str:
	normalized = normalizeText(rawText)
	hasColon = ":" in normalized
	if hasColon:
		parts = normalized.split(":", 1)
		result = parts[1].strip()
	else:
		result = normalized
	return result


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=30000)
			await page.wait_for_selector(".wpb_accordion_section", timeout=20000)
			panelLocator = page.locator(".wpb_accordion_section")
			panelCount = await panelLocator.count()
			index = 0
			while index < panelCount:
				currentPanel = panelLocator.nth(index)
				titleLocator = currentPanel.locator(".panel-title a span")
				titleCount = await titleLocator.count()
				hasTitle = titleCount > 0
				if hasTitle:
					titleText = await titleLocator.first.inner_text()
					title = normalizeText(titleText)
					hasNonEmptyTitle = title != ""
					if hasNonEmptyTitle:
						collapseLocator = currentPanel.locator(".panel-collapse")
						collapseCount = await collapseLocator.count()
						hasCollapse = collapseCount > 0
						if hasCollapse:
							panelSlug = await collapseLocator.first.get_attribute("id")
							hasPanelSlug = panelSlug is not None
							if not hasPanelSlug:
								panelSlug = ""
						else:
							panelSlug = ""
						specsLocator = currentPanel.locator(".job-specs")
						specsCount = await specsLocator.count()
						hasSpecs = specsCount > 0
						if hasSpecs:
							specsText = await specsLocator.first.inner_text()
							location, jobType = parseJobSpecs(specsText)
						else:
							location = ""
							jobType = ""
						applyLinkLocator = currentPanel.locator("a.custom-link")
						applyLinkCount = await applyLinkLocator.count()
						hasApplyLink = applyLinkCount > 0
						if hasApplyLink:
							href = await applyLinkLocator.first.get_attribute("href")
							hasHref = href is not None
							if not hasHref:
								href = ""
						else:
							href = ""
						dateLocator = currentPanel.locator(".job-date")
						dateCount = await dateLocator.count()
						hasDate = dateCount > 0
						if hasDate:
							dateText = await dateLocator.first.inner_text()
							postedAt = stripLabel(dateText)
						else:
							postedAt = ""
						stableId = extractStableId(href, panelSlug)
						jobId = generateJobId(title, stableId)
						job = {
							"id": jobId,
							"title": title,
							"link": href,
							"location": location,
							"department": "",
							"jobType": jobType,
							"postedAt": postedAt,
							"state": "open",
						}
						jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("constellationhb: fetchState failed: %s", error)
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
		logger.exception("constellationhb: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("constellationhb: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("constellationhb: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("constellationhb: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())