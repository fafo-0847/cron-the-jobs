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


sourceUrl = "https://tcpsoftware.com/careers/"
requestTimeoutSeconds = 60
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
tcpJsonPath = Path(__file__).with_name("tcp.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, shortcode: str) -> str:
	raw = title + shortcode
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def buildJobLink(shortcode: str) -> str:
	link = f"https://tcpsoftware.com/careers/?job={shortcode}"
	return link


async def parseJobItems(page) -> list[dict[str, str]]:
	items = page.locator(".wjb-job-item")
	count = await items.count()
	jobs: list[dict[str, str]] = []

	itemIndex = 0
	while itemIndex < count:
		item = items.nth(itemIndex)

		shortcode = (await item.get_attribute("data-shortcode") or "").strip()
		if not shortcode:
			itemIndex = itemIndex + 1
			continue

		titleEl = item.locator(".wjb-job-title").first
		title = (await titleEl.inner_text() or "").strip()

		country = (await item.get_attribute("data-country") or "").strip()
		city = (await item.get_attribute("data-city") or "").strip()
		locationEl = item.locator(".wjb-job-location").first
		location = (await locationEl.inner_text() or "").strip() if await locationEl.count() > 0 else ""

		department = (await item.get_attribute("data-department") or "").strip()

		remoteAttr = await item.get_attribute("data-remote")
		isRemote = remoteAttr == "1"
		jobType = "Remote" if isRemote else "On-site"

		link = buildJobLink(shortcode)

		if not title or not link:
			itemIndex = itemIndex + 1
			continue

		jobId = generateJobId(title, shortcode)

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
		itemIndex = itemIndex + 1

	return jobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching TCP jobs from %s", url)
	allJobs: list[dict[str, str]] = []

	async with async_playwright() as playwright:
		browser = await playwright.chromium.launch(headless=True)
		try:
			page = await browser.new_page(user_agent=userAgent)
			await page.goto(url, wait_until="domcontentloaded", timeout=requestTimeoutSeconds * 1000)

			try:
				await page.wait_for_selector(".wjb-job-item", timeout=30000)
			except Exception:
				logger.warning("No jobs found or timeout waiting for job listings.")
				allJobs = []
			else:
				allJobs = await parseJobItems(page)
				logger.info("Parsed %d total TCP jobs", len(allJobs))

		except Exception as error:
			logger.exception("Failed to fetch TCP jobs: %s", error)
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
	if not tcpJsonPath.exists():
		return defaultSnapshot()

	content = tcpJsonPath.read_text(encoding="utf-8")
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
	tcpJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated TCP snapshot at %s", tcpJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update TCP snapshot: %s", error)
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
