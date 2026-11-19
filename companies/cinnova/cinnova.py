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

companyName = "cinnova"
companyDir = Path(__file__).parent
snapshotPath = companyDir / f"{companyName}.json"

sourceUrl = "https://careers.cinnova.pk/current-openings/"

jobCardMarker = 'class="v1 sjb-job-'
jobIdPattern = re.compile(r'^(\d+)"')
jobTitlePattern = re.compile(r'<span class="job-title">(.*?)</span>', re.DOTALL)
jobLinkPattern = re.compile(r'<a href="([^"]+)">\s*<span class="job-title">', re.DOTALL)
jobLocationPattern = re.compile(r'<div class="job-location">.*?</i>(.*?)</div>', re.DOTALL)
jobDatePattern = re.compile(r'<div class="job-date">.*?</i>(.*?)</div>', re.DOTALL)
jobTypePattern = re.compile(r'<strong>Job Type:</strong>\s*(.*?)\s*<strong>', re.DOTALL)


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


def parseJobsFromHtml(htmlText: str) -> list:
	jobChunks = htmlText.split(jobCardMarker)
	newJobs = []
	index = 1
	while index < len(jobChunks):
		chunk = jobChunks[index]
		parsedJob = parseJobChunk(chunk)
		stableId = parsedJob.get("stableId", "")
		title = normalizeText(parsedJob.get("title", ""))
		hasStableIdAndTitle = stableId != "" and title != ""
		if hasStableIdAndTitle:
			jobId = generateJobId(title, stableId)
			job = {
				"id": jobId,
				"title": title,
				"link": parsedJob.get("link", ""),
				"location": normalizeText(parsedJob.get("location", "")),
				"department": "",
				"jobType": normalizeText(parsedJob.get("jobType", "")),
				"postedAt": normalizeText(parsedJob.get("postedAt", "")),
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
			await page.wait_for_selector(".sjb-listing", timeout=20000)
			await page.wait_for_timeout(1500)
			htmlText = await page.content()
			await browser.close()
	except Exception as error:
		logger.warning("Failed to fetch %s: %s", companyName, error)
	jobs = parseJobsFromHtml(htmlText)
	state = {"jobs": jobs}
	return state


def parseJobChunk(chunk: str) -> dict[str, Any]:
	idMatch = jobIdPattern.match(chunk)
	stableId = ""
	if idMatch is not None:
		stableId = idMatch.group(1)
	titleMatch = jobTitlePattern.search(chunk)
	rawTitle = ""
	if titleMatch is not None:
		rawTitle = titleMatch.group(1)
	linkMatch = jobLinkPattern.search(chunk)
	link = ""
	if linkMatch is not None:
		link = linkMatch.group(1)
	locationMatch = jobLocationPattern.search(chunk)
	rawLocation = ""
	if locationMatch is not None:
		rawLocation = locationMatch.group(1)
	dateMatch = jobDatePattern.search(chunk)
	rawPostedAt = ""
	if dateMatch is not None:
		rawPostedAt = dateMatch.group(1)
	jobTypeMatch = jobTypePattern.search(chunk)
	rawJobType = ""
	if jobTypeMatch is not None:
		rawJobType = jobTypeMatch.group(1)
	job = {
		"stableId": stableId,
		"title": rawTitle,
		"link": link,
		"location": rawLocation,
		"postedAt": rawPostedAt,
		"jobType": rawJobType,
	}
	return job


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