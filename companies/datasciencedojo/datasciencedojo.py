import asyncio
import hashlib
import html
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

companyName = "datasciencedojo"
companyDir = Path(__file__).parent
snapshotPath = companyDir / f"{companyName}.json"

sourceUrl = "https://datasciencedojo.com/about/careers/"

jobItemMarker = 'class="elementor-icon-list-item"'
jobLinkPattern = re.compile(r'<a href="([^"]+)"', re.DOTALL)
jobTitlePattern = re.compile(r'<span class="elementor-icon-list-text">(.*?)</span>', re.DOTALL)


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
	stripTagsPattern = re.compile(r'<[^>]+>')
	withoutTags = stripTagsPattern.sub("", text)
	unescaped = html.unescape(withoutTags)
	normalized = unescaped.replace("\xa0", " ").strip()
	return normalized


def extractSlugFromLink(link: str) -> str:
	trimmedLink = link.rstrip("/")
	segments = trimmedLink.split("/")
	hasSegments = len(segments) > 0
	if hasSegments:
		slug = segments[-1]
	else:
		slug = ""
	return slug


def parseJobsFromHtml(htmlText: str) -> list:
	jobChunks = htmlText.split(jobItemMarker)
	newJobs = []
	index = 1
	while index < len(jobChunks):
		chunk = jobChunks[index]
		linkMatch = jobLinkPattern.search(chunk)
		link = ""
		if linkMatch is not None:
			link = linkMatch.group(1)
		titleMatch = jobTitlePattern.search(chunk)
		rawTitle = ""
		if titleMatch is not None:
			rawTitle = titleMatch.group(1)
		title = normalizeText(rawTitle)
		isJobLink = "/jobs/" in link
		hasTitleAndLink = title != "" and link != ""
		if hasTitleAndLink and isJobLink:
			stableId = extractSlugFromLink(link)
			jobId = generateJobId(title, stableId)
			job = {
				"id": jobId,
				"title": title,
				"link": link,
				"location": "",
				"department": "",
				"jobType": "",
				"postedAt": "",
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
		logger.warning("Failed to fetch %s: %s", companyName, error)
	jobs = parseJobsFromHtml(htmlText)
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