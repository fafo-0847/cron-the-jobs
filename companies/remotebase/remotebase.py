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


sourceUrl = "https://remotebase.com/jobs"
requestTimeoutSeconds = 60
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
remotebaseJsonPath = Path(__file__).with_name("remotebase.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, eventKey: str) -> str:
	hasStableKey = eventKey != ""
	if hasStableKey:
		raw = title + eventKey
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def buildJobLink(eventKey: str) -> str:
	if not eventKey:
		return sourceUrl
	link = f"https://remotebase.com/jobs/{eventKey}"
	return link


async def parseJobTabs(page) -> list[dict[str, str]]:
	tabs = page.locator("a[data-rr-ui-event-key]")
	count = await tabs.count()
	jobs: list[dict[str, str]] = []

	tabIndex = 0
	while tabIndex < count:
		tab = tabs.nth(tabIndex)

		eventKey = (await tab.get_attribute("data-rr-ui-event-key") or "").strip()

		titleEl = tab.locator("h5").first
		title = (await titleEl.inner_text() or "").strip() if await titleEl.count() > 0 else ""

		locationEl = tab.locator("h6").first
		location = (await locationEl.inner_text() or "").strip() if await locationEl.count() > 0 else ""

		departmentEl = tab.locator("p").first
		department = (await departmentEl.inner_text() or "").strip() if await departmentEl.count() > 0 else ""

		if not title:
			tabIndex = tabIndex + 1
			continue

		link = buildJobLink(eventKey)
		jobId = generateJobId(title, eventKey)

		record = {
			"id": jobId,
			"title": title,
			"link": link,
			"location": location,
			"department": department,
			"jobType": "",
			"postedAt": "",
			"state": "open",
		}
		jobs.append(record)
		tabIndex = tabIndex + 1

	return jobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching Remotebase jobs from %s", url)
	allJobs: list[dict[str, str]] = []

	async with async_playwright() as playwright:
		browser = await playwright.chromium.launch(headless=True)
		try:
			page = await browser.new_page(user_agent=userAgent)
			await page.goto(url, wait_until="networkidle", timeout=requestTimeoutSeconds * 1000)
			await page.wait_for_timeout(2000)

			try:
				await page.wait_for_selector("a[data-rr-ui-event-key]", timeout=30000)
			except Exception:
				logger.warning("No jobs found or timeout waiting for job listings.")
				allJobs = []
			else:
				allJobs = await parseJobTabs(page)
				logger.info("Parsed %d total Remotebase jobs", len(allJobs))

		except Exception as error:
			logger.exception("Failed to fetch Remotebase jobs: %s", error)
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
	return {"sourceUrl": url, "fetchedAt": "", "state": "open", "jobs": []}


def loadExistingSnapshot() -> dict[str, Any]:
	if not remotebaseJsonPath.exists():
		return defaultSnapshot()
	content = remotebaseJsonPath.read_text(encoding="utf-8")
	if not content.strip():
		return defaultSnapshot()
	return json.loads(content)


def buildSnapshot(state: dict[str, Any], existingSnapshot: dict[str, Any]) -> dict[str, Any]:
	newJobs = state.get("jobs", [])
	oldJobs = existingSnapshot.get("jobs", [])

	suspiciousDrop = len(oldJobs) > 0 and len(newJobs) == 0
	if suspiciousDrop:
		logger.warning("Suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", len(oldJobs), len(newJobs))
		return dict(existingSnapshot)

	snapshot = dict(existingSnapshot)
	snapshot["sourceUrl"] = state.get("sourceUrl", sourceUrl)
	snapshot["fetchedAt"] = state.get("fetchedAt", "")
	snapshot["state"] = state.get("state", "open")
	snapshot["jobs"] = newJobs
	return snapshot


def writeSnapshot(snapshot: dict[str, Any]) -> None:
	output = json.dumps(snapshot, indent=2, ensure_ascii=False)
	remotebaseJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated Remotebase snapshot at %s", remotebaseJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update Remotebase snapshot: %s", error)
		snapshot = buildSnapshot(defaultSnapshot(url), existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		return snapshot


async def runMain() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--url", default=sourceUrl)
	args = parser.parse_args()

	snapshot = await updateSnapshot(args.url)
	print(json.dumps(snapshot, indent=2, ensure_ascii=False))


if __name__ == "__main__":
	asyncio.run(runMain())