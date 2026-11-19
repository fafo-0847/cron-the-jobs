from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from playwright.async_api import async_playwright


sourceUrl = "https://laam.peopleforce.io/careers"
requestTimeoutSeconds = 60
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
laamJsonPath = Path(__file__).with_name("laam.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, link: str) -> str:
	raw = title + link
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def parseMetaLine(metaText: str) -> tuple[str, str, str]:
	rawParts = metaText.split(",")
	cleanedParts: list[str] = []
	partIndex = 0
	while partIndex < len(rawParts):
		cleanedPart = rawParts[partIndex].strip()
		cleanedParts.append(cleanedPart)
		partIndex = partIndex + 1

	department = cleanedParts[0] if len(cleanedParts) > 0 else ""
	jobType = cleanedParts[1] if len(cleanedParts) > 1 else ""
	locationParts = cleanedParts[2:] if len(cleanedParts) > 2 else []
	location = ", ".join(locationParts)

	return department, jobType, location


async def parseJobCards(page) -> list[dict[str, str]]:
	cards = page.locator("#results .row.gy-3 > .col-12")
	count = await cards.count()
	jobs: list[dict[str, str]] = []

	cardIndex = 0
	while cardIndex < count:
		card = cards.nth(cardIndex)
		linkEl = card.locator("a.stretched-link").first
		hasLink = await linkEl.count() > 0
		if not hasLink:
			cardIndex = cardIndex + 1
			continue

		href = (await linkEl.get_attribute("href") or "").strip()
		link = urljoin(sourceUrl, href)
		title = (await linkEl.text_content() or "").strip()

		metaEl = card.locator(".tw-text-neutral-dark-80.small").first
		hasMeta = await metaEl.count() > 0
		metaText = (await metaEl.text_content() or "").strip() if hasMeta else ""

		department, jobType, location = parseMetaLine(metaText)

		if not title or not link:
			cardIndex = cardIndex + 1
			continue

		jobId = generateJobId(title, link)

		record = {
			"id": jobId,
			"title": title,
			"link": link,
			"location": location,
			"department": department,
			"jobType": jobType,
			"postedAt": "",
			"state": "open",
		}
		jobs.append(record)
		cardIndex = cardIndex + 1

	return jobs


async def getLastPageNumber(page) -> int:
	pageLinks = page.locator("nav.pagy-bootstrap-nav .page-item .page-link")
	count = await pageLinks.count()
	highestPage = 1

	linkIndex = 0
	while linkIndex < count:
		linkEl = pageLinks.nth(linkIndex)
		linkText = (await linkEl.text_content() or "").strip()
		if linkText.isdigit():
			pageNumber = int(linkText)
			if pageNumber > highestPage:
				highestPage = pageNumber
		linkIndex = linkIndex + 1

	return highestPage


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching Laam jobs from %s", url)
	allJobs: list[dict[str, str]] = []

	async with async_playwright() as playwright:
		browser = await playwright.chromium.launch(headless=True)
		try:
			page = await browser.new_page(user_agent=userAgent)
			await page.goto(url, wait_until="domcontentloaded", timeout=requestTimeoutSeconds * 1000)

			try:
				await page.wait_for_selector("#results .row.gy-3", timeout=30000)
			except Exception:
				logger.warning("No jobs found or timeout waiting for job listings.")
				allJobs = []
			else:
				lastPage = await getLastPageNumber(page)
				logger.info("Detected %d total pages", lastPage)

				currentPageNumber = 1
				while currentPageNumber <= lastPage:
					if currentPageNumber > 1:
						pageUrl = f"{url}?page={currentPageNumber}"
						await page.goto(pageUrl, wait_until="domcontentloaded", timeout=requestTimeoutSeconds * 1000)
						await page.wait_for_selector("#results .row.gy-3", timeout=30000)

					pageJobs = await parseJobCards(page)
					allJobs.extend(pageJobs)
					logger.info("Parsed %d jobs from page %d", len(pageJobs), currentPageNumber)
					currentPageNumber = currentPageNumber + 1

			logger.info("Parsed %d total Laam jobs", len(allJobs))
		except Exception as error:
			logger.exception("Failed to fetch Laam jobs: %s", error)
			allJobs = []
		finally:
			await browser.close()

	fetchedAt = datetime.now(timezone.utc).isoformat()
	state = {
		"sourceUrl": url,
		"fetchedAt": fetchedAt,
		"state": "open",
		"jobs": allJobs,
	}
	return state


def defaultSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	snapshot = {
		"sourceUrl": url,
		"fetchedAt": "",
		"state": "open",
		"jobs": [],
	}
	return snapshot


def loadExistingSnapshot() -> dict[str, Any]:
	if not laamJsonPath.exists():
		return defaultSnapshot()

	content = laamJsonPath.read_text(encoding="utf-8")
	if not content.strip():
		return defaultSnapshot()

	data = json.loads(content)
	return data


def buildSnapshot(state: dict[str, Any], existingSnapshot: dict[str, Any]) -> dict[str, Any]:
	snapshot = dict(existingSnapshot)
	snapshot["sourceUrl"] = state.get("sourceUrl", sourceUrl)
	snapshot["fetchedAt"] = state.get("fetchedAt", "")
	snapshot["state"] = state.get("state", "open")
	snapshot["jobs"] = state.get("jobs", [])
	return snapshot


def writeSnapshot(snapshot: dict[str, Any]) -> None:
	output = json.dumps(snapshot, indent=2, ensure_ascii=False)
	laamJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated Laam snapshot at %s", laamJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update Laam snapshot: %s", error)
		snapshot = buildSnapshot(defaultSnapshot(url), existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		return snapshot


async def runMain() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--url", default=sourceUrl)
	args = parser.parse_args()

	snapshot = await updateSnapshot(args.url)
	output = json.dumps(snapshot, indent=2, ensure_ascii=False)
	print(output)


if __name__ == "__main__":
	asyncio.run(runMain())
