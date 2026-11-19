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

sourceUrl = "https://curemd.wd1.myworkdayjobs.com/en-US/CureMD"
requestTimeoutSeconds = 60
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
curemdJsonPath = Path(__file__).with_name("curemd.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, jobCode: str, link: str) -> str:
	hasStableJobCode = jobCode != ""
	if hasStableJobCode:
		raw = title + jobCode
	else:
		raw = title + link
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


async def parseJobCards(page) -> list[dict[str, str]]:
	cards = page.locator('li.css-1q2dra3')
	cardCount = await cards.count()
	if cardCount == 0:
		cards = page.locator('ul[role="list"] > li')

	count = await cards.count()
	jobs: list[dict[str, str]] = []

	cardIndex = 0
	while cardIndex < count:
		card = cards.nth(cardIndex)

		titleEl = card.locator('a[data-automation-id="jobTitle"]')
		hasTitleEl = await titleEl.count() > 0
		if not hasTitleEl:
			cardIndex = cardIndex + 1
			continue

		href = (await titleEl.get_attribute("href") or "").strip()
		link = urljoin("https://curemd.wd1.myworkdayjobs.com", href)

		title = (await titleEl.text_content() or "").strip()

		locationEl = card.locator('div[data-automation-id="locations"] dd')
		location = (await locationEl.text_content() or "").strip() if await locationEl.count() > 0 else ""

		postedAtEl = card.locator('div[data-automation-id="postedOn"] dd')
		postedAt = (await postedAtEl.text_content() or "").strip() if await postedAtEl.count() > 0 else ""

		jobCodeEl = card.locator('ul[data-automation-id="subtitle"] li')
		jobCode = (await jobCodeEl.text_content() or "").strip() if await jobCodeEl.count() > 0 else ""

		if not title or not link:
			cardIndex = cardIndex + 1
			continue

		jobId = generateJobId(title, jobCode, link)

		record = {
			"id": jobId,
			"title": title,
			"link": link,
			"location": location,
			"postedAt": postedAt,
			"jobCode": jobCode,
			"state": "open",
		}
		jobs.append(record)
		cardIndex = cardIndex + 1

	return jobs

async def collectAllJobs(page) -> list[dict[str, str]]:
	allJobs: list[dict[str, str]] = []
	seenIds: set[str] = set()
	
	pageCount = 1

	while True:
		logger.info("Parsing page %d...", pageCount)
		jobs = await parseJobCards(page)
		newJobs = 0
		for job in jobs:
			if job["id"] not in seenIds:
				seenIds.add(job["id"])
				allJobs.append(job)
				newJobs += 1
		logger.info("Collected %d jobs so far (new on this page: %d)", len(allJobs), newJobs)

		nextBtn = page.locator('button[aria-label="next"]')
		if await nextBtn.count() == 0:
			nextBtn = page.locator('button[aria-label="Next"]')
			if await nextBtn.count() == 0:
				break

		isDisabled = await nextBtn.get_attribute("disabled")
		if isDisabled is not None or str(isDisabled).lower() == "true":
			break
			
		firstTitle = ""
		firstCard = page.locator('a[data-automation-id="jobTitle"]').first
		if await firstCard.count() > 0:
			firstTitle = (await firstCard.text_content() or "").strip()

		try:
			await nextBtn.click()
			pageCount += 1
		except Exception:
			logger.warning("Failed to click next page button")
			break

		try:
			await page.wait_for_function(
				"""(oldTitle) => {
					const el = document.querySelector('a[data-automation-id="jobTitle"]');
					if (!el) return false;
					return el.textContent.trim() !== oldTitle;
				}""",
				firstTitle,
				timeout=15000,
			)
		except Exception:
			logger.warning("Timed out waiting for page content to update")
			break

		await page.wait_for_timeout(500)

	return allJobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching CureMD jobs from %s", url)
	async with async_playwright() as playwright:
		browser = await playwright.chromium.launch(headless=True)
		try:
			page = await browser.new_page(user_agent=userAgent)
			await page.goto(url, wait_until="networkidle", timeout=requestTimeoutSeconds * 1000)

			try:
				await page.wait_for_selector('a[data-automation-id="jobTitle"]', timeout=30000)
			except Exception:
				logger.warning("No jobs found or timeout waiting for job listings.")
				jobs = []
			else:
				jobs = await collectAllJobs(page)
				
			logger.info("Parsed %d total CureMD jobs", len(jobs))
		except Exception as error:
			logger.exception("Failed to fetch CureMD jobs: %s", error)
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
	if not curemdJsonPath.exists():
		return defaultSnapshot()

	content = curemdJsonPath.read_text(encoding="utf-8")
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
	curemdJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated CureMD snapshot at %s", curemdJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update CureMD snapshot: %s", error)
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
