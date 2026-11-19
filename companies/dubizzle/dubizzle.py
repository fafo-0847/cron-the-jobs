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


sourceUrl = "https://jobs.dubizzlelabs.com"
requestTimeoutSeconds = 60
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
dubizzleJsonPath = Path(__file__).with_name("dubizzle.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, link: str) -> str:
	raw = title + link
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


async def parseJobCards(page) -> list[dict[str, str]]:
	cards = page.locator("ul.positions.location li.position")
	count = await cards.count()
	jobs: list[dict[str, str]] = []

	for i in range(count):
		card = cards.nth(i)
		details = card.locator("li.position-details a").first
		if await details.count() == 0:
			continue

		href = (await details.get_attribute("href") or "").strip()
		link = urljoin(sourceUrl, href)

		titleEl = details.locator("h2")
		title = (await titleEl.text_content() or "").strip()

		locationEl = details.locator("li.location span")
		location = (await locationEl.text_content() or "").strip() if await locationEl.count() > 0 else ""

		departmentEl = details.locator("li.department span")
		department = (await departmentEl.text_content() or "").strip() if await departmentEl.count() > 0 else ""

		if not title or not link:
			continue

		jobId = generateJobId(title, link)

		record = {
			"id": jobId,
			"title": title,
			"link": link,
			"location": location,
			"department": department,
			"postedAt": "",
			"state": "open",
		}
		jobs.append(record)

	return jobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching Dubizzle jobs from %s", url)
	async with async_playwright() as playwright:
		browser = await playwright.chromium.launch(headless=True)
		try:
			page = await browser.new_page(user_agent=userAgent)
			await page.goto(url, wait_until="domcontentloaded", timeout=requestTimeoutSeconds * 1000)

			try:
				await page.wait_for_selector("ul.positions.location li.position", timeout=30000)
			except Exception:
				logger.warning("No jobs found or timeout waiting for job listings.")
				jobs = []
			else:
				# Single page layout, no visible pagination in the HTML sample
				jobs = await parseJobCards(page)
				
			logger.info("Parsed %d total Dubizzle jobs", len(jobs))
		except Exception as error:
			logger.exception("Failed to fetch Dubizzle jobs: %s", error)
			jobs = []
		finally:
			await browser.close()

	fetchedAt = datetime.now(timezone.utc).isoformat()
	state = {
		"sourceUrl": url,
		"fetchedAt": fetchedAt,
		"state": "open",
		"jobs": jobs,
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
	if not dubizzleJsonPath.exists():
		return defaultSnapshot()

	content = dubizzleJsonPath.read_text(encoding="utf-8")
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
	dubizzleJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated Dubizzle snapshot at %s", dubizzleJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update Dubizzle snapshot: %s", error)
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
