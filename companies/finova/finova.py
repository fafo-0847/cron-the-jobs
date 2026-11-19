import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("finova")

sourceUrl = "https://careers.finova.tech/#jobs"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "finova.json"


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
		firstToken = tokens[0]
	else:
		firstToken = ""
	isNumeric = firstToken.isdigit()
	if isNumeric:
		stableId = firstToken
	else:
		stableId = slug
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
			await page.wait_for_selector("#jobs_list_container li", timeout=20000)
			itemLocator = page.locator("#jobs_list_container li")
			itemCount = await itemLocator.count()
			index = 0
			while index < itemCount:
				currentItem = itemLocator.nth(index)
				linkLocator = currentItem.locator("a")
				linkCount = await linkLocator.count()
				hasLink = linkCount > 0
				if hasLink:
					href = await linkLocator.first.get_attribute("href")
					hasHref = href is not None
					if not hasHref:
						href = ""
					titleSpanLocator = linkLocator.first.locator("span[title]")
					titleSpanCount = await titleSpanLocator.count()
					hasTitleSpan = titleSpanCount > 0
					if hasTitleSpan:
						titleAttr = await titleSpanLocator.first.get_attribute("title")
						hasTitleAttr = titleAttr is not None and titleAttr != ""
						if hasTitleAttr:
							title = normalizeText(titleAttr)
						else:
							titleText = await titleSpanLocator.first.inner_text()
							title = normalizeText(titleText)
						hasNonEmptyTitle = title != ""
						if hasNonEmptyTitle:
							metaSpanLocator = linkLocator.first.locator(".mt-1.text-md > span")
							metaSpanCount = await metaSpanLocator.count()
							metaValues = []
							metaIndex = 0
							while metaIndex < metaSpanCount:
								currentMetaSpan = metaSpanLocator.nth(metaIndex)
								classAttr = await currentMetaSpan.get_attribute("class")
								hasClassAttr = classAttr is not None
								if not hasClassAttr:
									classAttr = ""
								isSeparator = "mx-[2px]" in classAttr
								if not isSeparator:
									metaText = await currentMetaSpan.inner_text()
									metaValue = normalizeText(metaText)
									isDotOnly = metaValue == "·"
									if not isDotOnly:
										metaValues.append(metaValue)
								metaIndex = metaIndex + 1
							hasDepartment = len(metaValues) >= 1
							if hasDepartment:
								department = metaValues[0]
							else:
								department = ""
							hasLocation = len(metaValues) >= 2
							if hasLocation:
								location = metaValues[1]
							else:
								location = ""
							hasWorkplaceType = len(metaValues) >= 3
							if hasWorkplaceType:
								workplaceType = metaValues[2]
							else:
								workplaceType = ""
							stableId = extractStableId(href)
							jobId = generateJobId(title, stableId)
							job = {
								"id": jobId,
								"title": title,
								"link": href,
								"location": location,
								"department": department,
								"jobType": workplaceType,
								"postedAt": "",
								"state": "open",
							}
							jobs.append(job)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.exception("finova: fetchState failed: %s", error)
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
		logger.exception("finova: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("finova: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
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
		logger.exception("finova: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("finova: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())