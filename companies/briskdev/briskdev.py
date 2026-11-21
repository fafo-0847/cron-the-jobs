import hashlib
import json
import logging
import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("briskdev")

sourceUrl = "https://briskdev.co/careers/"
companyDir = Path(__file__).parent
snapshotPath = companyDir / "briskdev.json"


def generateJobId(title: str, description: str) -> str:
	raw = title + "|" + description
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def normalizeText(rawText) -> str:
	isNone = rawText is None
	if isNone:
		return ""
	normalized = rawText.replace("\xa0", " ").strip()
	return normalized


# Nov 2026: /career/ is a WordPress 404 ("Page not found"); the new site is a client-rendered
# React app at /careers/. Each role is <a href="/careers/<slug>"><h3>Title</h3>
# <p>Team · Location · Type</p></a>. The slug is used as the stable id.
siteUrl = "https://briskdev.co"
roleLinkSelector = "a[href^='/careers/']:has(h3)"


def parseMetaLine(metaText: str) -> tuple[str, str, str]:
	parts = [part.strip() for part in metaText.split("·")]
	department = parts[0] if len(parts) > 0 else ""
	location = parts[1] if len(parts) > 1 else ""
	jobType = parts[2] if len(parts) > 2 else ""
	return department, location, jobType


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	jobs = []
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page()
			await page.goto(url, wait_until="domcontentloaded", timeout=30000)
			await page.wait_for_selector(roleLinkSelector, state="attached", timeout=20000)
			roleLocator = page.locator(roleLinkSelector)
			roleCount = await roleLocator.count()
			for index in range(roleCount):
				role = roleLocator.nth(index)
				title = normalizeText(await role.locator("h3").first.text_content())
				href = await role.get_attribute("href") or ""
				if title == "" or href == "":
					continue
				metaLocator = role.locator("p")
				metaText = normalizeText(await metaLocator.first.text_content()) if await metaLocator.count() > 0 else ""
				department, location, jobType = parseMetaLine(metaText)
				slug = href.rstrip("/").split("/")[-1]
				jobs.append({
					"id": generateJobId(title, slug),
					"title": title,
					"link": siteUrl + href,
					"location": location,
					"department": department,
					"jobType": jobType,
					"postedAt": "",
					"state": "open",
				})
			await browser.close()
	except Exception as error:
		logger.exception("briskdev: fetchState failed: %s", error)
	state = {"jobs": jobs, "state": "open"}
	return state


def loadExistingSnapshot() -> dict[str, Any]:
	try:
		fileExists = snapshotPath.exists()
		if not fileExists:
			return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}
		rawText = snapshotPath.read_text(encoding="utf-8")
		snapshot = json.loads(rawText)
		return snapshot
	except Exception as error:
		logger.exception("briskdev: loadExistingSnapshot failed: %s", error)
		return {"sourceUrl": sourceUrl, "fetchedAt": "", "state": "open", "jobs": []}


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	newJobs = state.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("briskdev: suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
		return dict(existingSnapshot)
	fetchedAt = datetime.datetime.now(datetime.timezone.utc).isoformat()
	snapshot = {
		"sourceUrl": sourceUrl,
		"fetchedAt": fetchedAt,
		"state": state.get("state", "open"),
		"jobs": newJobs,
	}
	return snapshot


def writeSnapshot(snapshot: dict) -> None:
	try:
		snapshotText = json.dumps(snapshot, indent=2, ensure_ascii=False)
		snapshotPath.write_text(snapshotText, encoding="utf-8")
	except Exception as error:
		logger.exception("briskdev: writeSnapshot failed: %s", error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("briskdev: run complete, %d jobs in snapshot", jobCount)


if __name__ == "__main__":
	import asyncio
	asyncio.run(runMain())