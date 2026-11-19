import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

companyName = "uworx"
companyDir = Path(__file__).parent
snapshotPath = companyDir / f"{companyName}.json"

sourceUrl = "https://uworx.webhr.co/hr/careers/"

cardSelector = ".ant-card.ant-card-bordered.ant-card-hoverable"


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def loadExistingSnapshot() -> dict[str, Any]:
	fileExists = snapshotPath.exists()
	if fileExists:
		try:
			rawText = snapshotPath.read_text()
			snapshot = json.loads(rawText)
			return snapshot
		except Exception as error:
			logger.warning("Failed to load existing snapshot for %s: %s", companyName, error)
			return {"jobs": []}
	else:
		return {"jobs": []}


def normalizeText(text: str) -> str:
	normalized = text.replace("\xa0", " ").strip()
	return normalized


def parseJobsFromCards(cards: list) -> list:
	newJobs = []
	index = 0
	while index < len(cards):
		card = cards[index]
		title = normalizeText(card.get("title", ""))
		jobType = normalizeText(card.get("jobType", ""))
		closingDate = normalizeText(card.get("closingDate", ""))
		compositeStableId = jobType + closingDate
		jobId = generateJobId(title, compositeStableId)
		job = {
			"id": jobId,
			"title": title,
			"link": sourceUrl,
			"location": "",
			"department": "",
			"jobType": jobType,
			"postedAt": "",
			"closingDate": closingDate,
			"state": "open",
		}
		newJobs.append(job)
		index = index + 1
	return newJobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	cards = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="networkidle")
			await page.wait_for_selector(cardSelector, timeout=20000)
			await page.wait_for_timeout(2000)
			cardElements = await page.query_selector_all(cardSelector)
			index = 0
			while index < len(cardElements):
				cardElement = cardElements[index]
				titleElement = await cardElement.query_selector(".ant-card-meta-title")
				rawTitle = ""
				if titleElement is not None:
					rawTitle = await titleElement.inner_text()
				valueElements = await cardElement.query_selector_all(".value-0-2-14")
				rawJobType = ""
				rawClosingDate = ""
				valueTexts = []
				valueIndex = 0
				while valueIndex < len(valueElements):
					valueElement = valueElements[valueIndex]
					valueText = await valueElement.inner_text()
					valueTexts.append(valueText)
					valueIndex = valueIndex + 1
				hasJobType = len(valueTexts) > 0
				if hasJobType:
					rawJobType = valueTexts[0]
				hasClosingDate = len(valueTexts) > 1
				if hasClosingDate:
					rawClosingDate = valueTexts[1]
				card = {
					"title": rawTitle,
					"jobType": rawJobType,
					"closingDate": rawClosingDate,
				}
				cards.append(card)
				index = index + 1
			await browser.close()
	except Exception as error:
		logger.warning("Failed to fetch %s: %s", companyName, error)
	jobs = parseJobsFromCards(cards)
	state = {"jobs": jobs}
	return state


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobs = state.get("jobs", [])
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("Suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
		return dict(existingSnapshot)
	snapshot = {
		"sourceUrl": sourceUrl,
		"fetchedAt": datetime.now(timezone.utc).isoformat(),
		"state": "open",
		"jobs": newJobs,
	}
	return snapshot


def writeSnapshot(snapshot: dict) -> None:
	try:
		snapshotText = json.dumps(snapshot, indent=2)
		snapshotPath.write_text(snapshotText)
	except Exception as error:
		logger.warning("Failed to write snapshot for %s: %s", companyName, error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	logging.basicConfig(level=logging.INFO)
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("Fetched %d jobs for %s", jobCount, companyName)


if __name__ == "__main__":
	asyncio.run(runMain())