import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

companyName = "barq"
companyDir = Path(__file__).parent
snapshotPath = companyDir / f"{companyName}.json"

siteBase = "https://barq.dev"
sourceUrl = f"{siteBase}/careers"

jobBlockPattern = re.compile(
	r'<h3 class="font-nunito[^"]*">(.*?)</h3>.*?'
	r'<div class="font-inter[^"]*">\s*<div>(.*?)</div>\s*</div>'
	r'<a class="[^"]*" href="(/careers/[^"]*)">',
	re.DOTALL,
)


# Nov 2026 redesign (CSS modules): <a class="careers_roleLink__x" href="/careers/<slug>"><div>
# <h3 ...>Title</h3><p class="careers_summary__x ...">Summary</p></div>...</a>
roleLinkPattern = re.compile(
	r'<a class="careers_roleLink[^"]*"[^>]*href="(/careers/[^"]+)"[^>]*>\s*<div>\s*'
	r'<h3[^>]*>(.*?)</h3>\s*(?:<p[^>]*>(.*?)</p>)?',
	re.DOTALL,
)
tagPattern = re.compile(r"<[^>]+>")


def generateJobId(title: str, stableId: str) -> str:
	hasStableId = stableId != ""
	if hasStableId:
		raw = title + stableId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def loadExistingSnapshot() -> dict[str, Any]:
	fileExists = snapshotPath.exists()
	if fileExists:
		try:
			rawText = snapshotPath.read_text()
			snapshot = json.loads(rawText)
			return snapshot
		except Exception as error:
			logger.warning("Failed to load existing snapshot for %s: %s", companyName, error)
			return {"jobs": []}
	else:
		return {"jobs": []}


def normalizeText(text: str) -> str:
	normalized = text.replace("\xa0", " ").strip()
	return normalized


def parseJobsFromHtml(htmlText: str) -> list:
	matches = jobBlockPattern.findall(htmlText)
	if len(matches) == 0:
		matches = [
			(tagPattern.sub("", title), tagPattern.sub("", summary or ""), slug)
			for slug, title, summary in roleLinkPattern.findall(htmlText)
		]
	newJobs = []
	index = 0
	while index < len(matches):
		match = matches[index]
		rawTitle = match[0]
		rawDescription = match[1]
		slug = match[2]
		title = normalizeText(rawTitle)
		description = normalizeText(rawDescription)
		stableId = slug
		jobId = generateJobId(title, stableId)
		link = siteBase + slug
		job = {
			"id": jobId,
			"title": title,
			"link": link,
			"location": "",
			"department": "",
			"jobType": "",
			"postedAt": "",
			"description": description,
			"state": "open",
		}
		newJobs.append(job)
		index = index + 1
	return newJobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	htmlText = ""
	try:
		async with async_playwright() as playwright:
			browser = await playwright.chromium.launch()
			page = await browser.new_page(
				user_agent=(
					"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
					"(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
				)
			)
			await page.goto(url, wait_until="networkidle", timeout=45000)
			await page.wait_for_timeout(1500)
			htmlText = await page.content()
			await browser.close()
	except Exception as error:
		logger.exception("Failed to fetch %s: %s", companyName, error)
	jobs = parseJobsFromHtml(htmlText)
	if htmlText != "" and len(jobs) == 0:
		logger.error("%s: careers page loaded but no roles parsed (layout changed?)", companyName)
	state = {"jobs": jobs}
	return state


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	oldJobs = existingSnapshot.get("jobs", [])
	oldJobCount = len(oldJobs)
	newJobs = state.get("jobs", [])
	newJobCount = len(newJobs)
	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("Suspicious zero-job scrape, keeping old snapshot. Old=%d New=%d", oldJobCount, newJobCount)
		return dict(existingSnapshot)
	snapshot = {
		"sourceUrl": sourceUrl,
		"fetchedAt": datetime.now(timezone.utc).isoformat(),
		"state": "open",
		"jobs": newJobs,
	}
	return snapshot


def writeSnapshot(snapshot: dict) -> None:
	try:
		snapshotText = json.dumps(snapshot, indent=2)
		snapshotPath.write_text(snapshotText)
	except Exception as error:
		logger.warning("Failed to write snapshot for %s: %s", companyName, error)


async def updateSnapshot(url: str = sourceUrl) -> dict:
	existingSnapshot = loadExistingSnapshot()
	state = await fetchState(url)
	snapshot = buildSnapshot(state, existingSnapshot)
	writeSnapshot(snapshot)
	return snapshot


async def runMain() -> None:
	logging.basicConfig(level=logging.INFO)
	snapshot = await updateSnapshot()
	jobCount = len(snapshot.get("jobs", []))
	logger.info("Fetched %d jobs for %s", jobCount, companyName)


if __name__ == "__main__":
	asyncio.run(runMain())