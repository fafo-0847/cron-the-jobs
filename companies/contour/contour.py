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


sourceUrl = "https://contour-software.com/jobs/"
requestTimeoutSeconds = 60
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
contourJsonPath = Path(__file__).with_name("contour.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, link: str) -> str:
	raw = title + link
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def buildJobLink(dataPath: str) -> str:
	if not dataPath:
		return ""
	link = f"https://contour-software.com/job-detail/?jobPath={dataPath}"
	return link


async def parseJobCards(page) -> list[dict[str, str]]:
	cards = page.locator("div.job-item.job-container")
	count = await cards.count()
	jobs: list[dict[str, str]] = []

	for i in range(count):
		card = cards.nth(i)

		titleEl = card.locator("h2")
		title = (await titleEl.text_content() or "").strip()

		paragraphs = card.locator("div.dyn_content_Wrap p")
		pCount = await paragraphs.count()

		location = ""
		postedAt = ""
		jobCode = ""

		for p in range(pCount):
			text = (await paragraphs.nth(p).text_content() or "").strip()
			if text.startswith("Location:"):
				location = text.replace("Location:", "").strip()
			elif text.startswith("Posted:"):
				postedAt = text.replace("Posted:", "").strip()
			elif text.startswith("Job Code:"):
				jobCode = text.replace("Job Code:", "").strip()

		btn = card.locator("button.view-job-btn")
		dataPath = await btn.get_attribute("data-path") or ""
		link = buildJobLink(dataPath)
		jobId = generateJobId(title, link)

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

		paginationSummary = page.locator("#pagination-summary")
		summaryText = (await paginationSummary.text_content() or "").strip()
		logger.info("Pagination: %s", summaryText)

		activeLi = page.locator("#pagination li.active")
		activeCount = await activeLi.count()
		if activeCount == 0:
			break

		nextLi = activeLi.locator("xpath=following-sibling::li[1]")
		nextExists = await nextLi.count()
		if nextExists == 0:
			break

		nextLink = nextLi.locator("a")
		nextText = (await nextLink.text_content() or "").strip()

		if nextText == "\u00bb":
			await nextLink.click()
		else:
			await nextLink.click()

		firstTitle = ""
		firstCard = page.locator("div.job-item.job-container h2").first
		if await firstCard.count() > 0:
			firstTitle = (await firstCard.text_content() or "").strip()

		try:
			await page.wait_for_function(
				"""(oldTitle) => {
					const el = document.querySelector('div.job-item.job-container h2');
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
	logger.info("Fetching Contour jobs from %s", url)
	async with async_playwright() as playwright:
		browser = await playwright.chromium.launch(headless=True)
		try:
			page = await browser.new_page(user_agent=userAgent)
			await page.goto(url, wait_until="networkidle", timeout=requestTimeoutSeconds * 1000)

			await page.wait_for_selector("div.job-item.job-container", timeout=30000)

			jobs = await collectAllJobs(page)
			logger.info("Parsed %d total Contour jobs", len(jobs))
		except Exception as error:
			logger.exception("Failed to fetch Contour jobs: %s", error)
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
	if not contourJsonPath.exists():
		return defaultSnapshot()

	content = contourJsonPath.read_text(encoding="utf-8")
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
	contourJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated Contour snapshot at %s", contourJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update Contour snapshot: %s", error)
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
