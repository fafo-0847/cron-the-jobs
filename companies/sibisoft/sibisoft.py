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

from companies._shared import emptyboard

logger = logging.getLogger(__name__)

companyName = "sibisoft"
companyDir = Path(__file__).parent
snapshotPath = companyDir / f"{companyName}.json"

noVacanciesPattern = re.compile(r"no vacancies available", re.I)
sourceUrl = "https://app.myhcm.pk/CareerPortal/Careers?q=S57nvxmYbMdN17VpCEUmkA%3D%3D&lang=null"

jobCardMarker = 'class="hcm-jpp-job"'
rrfCodePattern = re.compile(r'data-rrf-code="([^"]+)"')
jobTitlePattern = re.compile(r'class="hcm-jpp-name">\s*<span[^>]*>(.*?)</span>', re.DOTALL)
jobCompanyPattern = re.compile(r'class="hcm-jpp-company">(.*?)</div>', re.DOTALL)
jobLocationPattern = re.compile(r'class="hcm-jpp-location">.*?<span[^>]*>(.*?)</span>', re.DOTALL)
closingDatePattern = re.compile(r'class="hcm-jpp-closing_date">.*?</span><span>(.*?)</span>', re.DOTALL)


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
		rrfCodeMatch = rrfCodePattern.search(chunk)
		stableId = ""
		if rrfCodeMatch is not None:
			stableId = rrfCodeMatch.group(1)
		titleMatch = jobTitlePattern.search(chunk)
		rawTitle = ""
		if titleMatch is not None:
			rawTitle = titleMatch.group(1)
		title = normalizeText(rawTitle)
		companyMatch = jobCompanyPattern.search(chunk)
		rawDepartment = ""
		if companyMatch is not None:
			rawDepartment = companyMatch.group(1)
		locationMatch = jobLocationPattern.search(chunk)
		rawLocation = ""
		if locationMatch is not None:
			rawLocation = locationMatch.group(1)
		closingDateMatch = closingDatePattern.search(chunk)
		rawClosingDate = ""
		if closingDateMatch is not None:
			rawClosingDate = closingDateMatch.group(1)
		hasStableIdAndTitle = stableId != "" and title != ""
		if hasStableIdAndTitle:
			jobId = generateJobId(title, stableId)
			job = {
				"id": jobId,
				"title": title,
				"link": sourceUrl,
				"location": normalizeText(rawLocation),
				"department": normalizeText(rawDepartment),
				"jobType": "",
				"postedAt": "",
				"closingDate": normalizeText(rawClosingDate),
				"state": "open",
			}
			newJobs.append(job)
		index = index + 1
	return newJobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	htmlText = ""
	confirmedEmpty = False
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
			# MiHCM shows "There are no vacancies available at this time." when empty (seen Nov 2026).
			confirmedEmpty = await emptyboard.waitForJobsOrEmptyNotice(page, ".hcm-jpp-job", noVacanciesPattern, 20000)
			await page.wait_for_timeout(1500)
			htmlText = await page.content()
			await browser.close()
	except Exception as error:
		logger.exception("Failed to fetch %s: %s", companyName, error)
		confirmedEmpty = False
	jobs = [] if confirmedEmpty else parseJobsFromHtml(htmlText)
	state = {"jobs": jobs, "confirmedEmpty": confirmedEmpty and len(jobs) == 0}
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