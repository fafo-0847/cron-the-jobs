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

from companies._shared import browser as sharedBrowser


sourceUrl = "https://careers.tkxel.com/jobs/"
requestTimeoutSeconds = 60
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
tkxelJsonPath = Path(__file__).with_name("tkxel.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, link: str) -> str:
	raw = title + link
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


async def parseJobCards(page) -> list[dict[str, str]]:
	cards = page.locator(".jobs-cards-wrp .job-card")
	count = await cards.count()
	jobs: list[dict[str, str]] = []

	cardIndex = 0
	while cardIndex < count:
		card = cards.nth(cardIndex)

		linkEl = card.locator("a").first
		hasLink = await linkEl.count() > 0
		if not hasLink:
			cardIndex = cardIndex + 1
			continue

		href = (await linkEl.get_attribute("href") or "").strip()
		link = urljoin(sourceUrl, href)

		titleEl = card.locator(".job-title h6").first
		title = (await titleEl.inner_text() or "").strip()

		locationEl = card.locator(".job-location p").first
		location = (await locationEl.inner_text() or "").strip() if await locationEl.count() > 0 else ""

		if not title or not link:
			cardIndex = cardIndex + 1
			continue

		jobId = generateJobId(title, link)

		record = {
			"id": jobId,
			"title": title,
			"link": link,
			"location": location,
			"department": "",
			"jobType": "",
			"postedAt": "",
			"state": "open",
		}
		jobs.append(record)
		cardIndex = cardIndex + 1

	return jobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching TKXEL jobs from %s", url)
	allJobs: list[dict[str, str]] = []

	async with async_playwright() as playwright:
		browser = await playwright.chromium.launch(headless=True)
		try:
			page = await sharedBrowser.newPage(browser)
			await sharedBrowser.gotoChecked(page, url, waitUntil="domcontentloaded", timeoutMs=requestTimeoutSeconds * 1000)

			try:
				await page.wait_for_selector(".jobs-cards-wrp .job-card", timeout=30000)
			except Exception:
				logger.warning("No jobs found or timeout waiting for job listings.")
				allJobs = []
			else:
				allJobs = await parseJobCards(page)
				logger.info("Parsed %d total TKXEL jobs", len(allJobs))

		except Exception as error:
			logger.exception("Failed to fetch TKXEL jobs: %s", error)
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
	if not tkxelJsonPath.exists():
		return defaultSnapshot()

	content = tkxelJsonPath.read_text(encoding="utf-8")
	if not content.strip():
		return defaultSnapshot()

	data = json.loads(content)
	return data


def buildSnapshot(state: dict[str, Any], existingSnapshot: dict[str, Any]) -> dict[str, Any]:
	newJobs = state.get("jobs", [])
	oldJobs = existingSnapshot.get("jobs", [])

	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)

	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("Suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
		snapshot = dict(existingSnapshot)
		return snapshot

	snapshot = dict(existingSnapshot)
	snapshot["sourceUrl"] = state.get("sourceUrl", sourceUrl)
	snapshot["fetchedAt"] = state.get("fetchedAt", "")
	snapshot["state"] = state.get("state", "open")
	snapshot["jobs"] = newJobs
	return snapshot


def writeSnapshot(snapshot: dict[str, Any]) -> None:
	output = json.dumps(snapshot, indent=2, ensure_ascii=False)
	tkxelJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated TKXEL snapshot at %s", tkxelJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update TKXEL snapshot: %s", error)
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