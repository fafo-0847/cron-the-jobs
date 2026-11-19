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

sourceUrl = "https://www.gosaas.ai/careers"
requestTimeoutSeconds = 60
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
gosaasJsonPath = Path(__file__).with_name("gosaas.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, link: str) -> str:
	raw = title + link
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


async def parseJobCards(page) -> list[dict[str, str]]:
	cards = page.locator("div.listing__item div.content-card")
	count = await cards.count()
	jobs: list[dict[str, str]] = []

	for i in range(count):
		card = cards.nth(i)

		linkEl = card.locator("a.content-card__link")
		if await linkEl.count() == 0:
			continue

		href = (await linkEl.get_attribute("href") or "").strip()
		link = urljoin(sourceUrl, href)

		titleEl = card.locator("h4.content-card__title-tag")
		title = (await titleEl.text_content() or "").strip() if await titleEl.count() > 0 else ""

		locationEl = card.locator("div.content-card__label")
		location = (await locationEl.text_content() or "").strip() if await locationEl.count() > 0 else ""
		logger.info("Found job: %s, Location: '%s'", title, location)

		if not title or not link:
			continue

		# Only fetch jobs for Pakistan
		if location.lower() != "pakistan":
			continue

		jobId = generateJobId(title, link)

		record = {
			"id": jobId,
			"title": title,
			"link": link,
			"location": location,
			"postedAt": "",
			"state": "open",
		}
		jobs.append(record)

	return jobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching GoSaaS jobs from %s", url)
	async with async_playwright() as playwright:
		browser = await playwright.chromium.launch(headless=True)
		try:
			page = await browser.new_page(user_agent=userAgent)
			await page.goto(url, wait_until="domcontentloaded", timeout=requestTimeoutSeconds * 1000)

			try:
				await page.wait_for_selector("div.listing__item div.content-card", timeout=30000)
			except Exception:
				logger.warning("No jobs found or timeout waiting for job listings.")
				jobs = []
			else:
				# Click Pakistan filter
				pakistanBtn = page.locator("a[filter-category-eq='Pakistan']")
				if await pakistanBtn.count() > 0:
					await pakistanBtn.click()
					await page.wait_for_timeout(2000)

				jobs = []
				seenIds = set()
				pageCount = 1

				while True:
					logger.info("Parsing GoSaaS page %d...", pageCount)
					pageJobs = await parseJobCards(page)
					newJobs = 0
					for job in pageJobs:
						if job["id"] not in seenIds:
							seenIds.add(job["id"])
							jobs.append(job)
							newJobs += 1
					logger.info("Collected %d jobs so far (new on this page: %d)", len(jobs), newJobs)

					if pageCount > 1 and newJobs == 0:
						logger.info("No new jobs found on this page, ending pagination.")
						break

					# Look for the active pagination item, then find the next one
					activePageLi = page.locator("ul.listing__pagination li.active")
					if await activePageLi.count() == 0:
						break
						
					# Check if there is a next page element using a simple JS evaluation
					is_valid_next = await page.evaluate(
						"() => { const active = document.querySelector('ul.listing__pagination li.active'); return active && active.nextElementSibling && active.nextElementSibling.tagName === 'LI' && active.nextElementSibling.querySelector('a.page') !== null; }"
					)
					
					if not is_valid_next:
						break
					
					nextPageLink = page.locator("ul.listing__pagination li.active + li a.page")
					if await nextPageLink.count() == 0:
						break

					firstTitle = ""
					firstCard = page.locator("h4.content-card__title-tag").first
					if await firstCard.count() > 0:
						firstTitle = (await firstCard.text_content() or "").strip()

					try:
						await nextPageLink.click()
						pageCount += 1
						await page.wait_for_timeout(3000)
					except Exception:
						logger.warning("Failed to click next page button")
						break
					
					# The loop will naturally break if newJobs == 0 on the next iteration
					# which means the page didn't change or there are no new jobs for this filter
				
			logger.info("Parsed %d total GoSaaS jobs (Pakistan)", len(jobs))
		except Exception as error:
			logger.exception("Failed to fetch GoSaaS jobs: %s", error)
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
	if not gosaasJsonPath.exists():
		return defaultSnapshot()

	content = gosaasJsonPath.read_text(encoding="utf-8")
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
	gosaasJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated GoSaaS snapshot at %s", gosaasJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update GoSaaS snapshot: %s", error)
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
