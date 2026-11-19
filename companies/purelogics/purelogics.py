from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright


sourceUrl = "https://purelogics.com/careers/"
requestTimeoutSeconds = 60
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
purelogicsJsonPath = Path(__file__).with_name("purelogics.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, link: str) -> str:
	raw = title + link
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


async def parseJobCards(page) -> list[dict[str, str]]:
	cards = page.locator("li.job_listing")
	count = await cards.count()
	jobs: list[dict[str, str]] = []

	for i in range(count):
		card = cards.nth(i)

		linkEl = card.locator("a").first
		link = (await linkEl.get_attribute("href") or "").strip()

		titleEl = card.locator("div.position h3")
		title = (await titleEl.text_content() or "").strip()

		locationEl = card.locator("div.location")
		location = (await locationEl.text_content() or "").strip()

		timeEl = card.locator("ul.meta li.date time")
		if await timeEl.count() > 0:
			postedAt = (await timeEl.get_attribute("datetime") or "").strip()
			if not postedAt:
				postedAt = (await timeEl.text_content() or "").strip()
		else:
			postedAt = ""

		if not title or not link:
			continue

		jobId = generateJobId(title, link)

		record = {
			"id": jobId,
			"title": title,
			"link": link,
			"location": location,
			"postedAt": postedAt,
			"state": "open",
		}
		jobs.append(record)

	return jobs


async def collectAllJobs(page) -> list[dict[str, str]]:
	allJobs: list[dict[str, str]] = []
	seenIds: set[str] = set()

	while True:
		jobs = await parseJobCards(page)
		newJobs = 0
		for job in jobs:
			if job["id"] not in seenIds:
				seenIds.add(job["id"])
				allJobs.append(job)
				newJobs += 1
		logger.info("Collected %d jobs so far (new on this page: %d)", len(allJobs), newJobs)

		loadMoreBtn = page.locator("a.load_more_jobs")
		btnExists = await loadMoreBtn.count()
		
		if btnExists == 0:
			break
			
		isVisible = await loadMoreBtn.is_visible()
		if not isVisible:
			break

		try:
			await loadMoreBtn.click()
		except Exception:
			logger.warning("Failed to click load more button")
			break

		try:
			previousCount = len(jobs)
			await page.wait_for_function(
				f"""() => {{
					const els = document.querySelectorAll('li.job_listing');
					const btn = document.querySelector('a.load_more_jobs');
					return els.length > {previousCount} || !btn || btn.style.display === 'none' || btn.classList.contains('loading');
				}}""",
				timeout=15000,
			)
			# Small additional wait if there is a loading class that we need to wait to finish
			await page.wait_for_function(
				"""() => {
					const btn = document.querySelector('a.load_more_jobs');
					return !btn || !btn.classList.contains('loading');
				}""",
				timeout=15000,
			)
		except Exception:
			logger.warning("Timed out waiting for next page to load")
			break

		await page.wait_for_timeout(500)

	return allJobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching PureLogics jobs from %s", url)
	async with async_playwright() as playwright:
		browser = await playwright.chromium.launch(headless=True)
		try:
			page = await browser.new_page(user_agent=userAgent)
			await page.goto(url, wait_until="networkidle", timeout=requestTimeoutSeconds * 1000)

			try:
				await page.wait_for_selector("li.job_listing", timeout=30000)
			except Exception:
				logger.warning("No jobs found or timeout waiting for job listings.")
				jobs = []
			else:
				jobs = await collectAllJobs(page)
				
			logger.info("Parsed %d total PureLogics jobs", len(jobs))
		except Exception as error:
			logger.exception("Failed to fetch PureLogics jobs: %s", error)
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
	if not purelogicsJsonPath.exists():
		return defaultSnapshot()

	content = purelogicsJsonPath.read_text(encoding="utf-8")
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
	purelogicsJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated PureLogics snapshot at %s", purelogicsJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update PureLogics snapshot: %s", error)
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
