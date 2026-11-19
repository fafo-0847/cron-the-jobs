from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import logging
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from playwright.async_api import async_playwright


sourceUrl = "https://career55.sapsf.eu/career?company=systemvent&career_ns=job_listing_summary&navBarLevel=JOB_SEARCH"
requestTimeoutSeconds = 30
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
systemsJsonPath = Path(__file__).with_name("systems.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def findFirstMatch(pattern: str, text: str) -> str:
	match = re.search(pattern, text, flags=re.I | re.S)
	if match is None:
		return ""
	return unescape(match.group(1)).strip()


def generateJobId(title: str, reqId: str) -> str:
	hasStableReqId = reqId != ""
	if hasStableReqId:
		raw = title + reqId
	else:
		raw = title
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def extractFieldValues(articleHtml: str, label: str) -> str:
	pattern = rf'<span[^>]*aria-label="{label} \(\d+\)"[^>]*onclick="[^"]*\[([^\]]+)\]'
	valuesText = findFirstMatch(pattern, articleHtml)
	if not valuesText:
		return ""
	decodedValuesText = unescape(valuesText)
	values = re.findall(r'"([^"]+)"', decodedValuesText)
	joinedValues = ", ".join(values)
	return joinedValues


def extractExperience(articleHtml: str) -> str:
	values = re.findall(r'<span[^>]*class=["\']jobContentEM["\'][^>]*>([^<]+)</span>', articleHtml, flags=re.I | re.S)
	filteredValues: list[str] = []
	for value in values:
		text = unescape(value).strip()
		if not text:
			continue
		if text.lower().startswith("posted on"):
			continue
		if text.isdigit():
			continue
		filteredValues.append(text)

	if not filteredValues:
		return ""

	return filteredValues[-1]


def extractArticles(html: str) -> list[str]:
	articles: list[str] = []
	pattern = re.compile(r"<tr\b[^>]*class=[\"'][^\"']*jobResultItem[^\"']*[\"'][^>]*>.*?</tr>", re.I | re.S)
	matches = pattern.finditer(html)
	for match in matches:
		articles.append(match.group(0))
	return articles


def parseArticle(articleHtml: str) -> dict[str, str]:
	title = findFirstMatch(r"<a[^>]*class=[\"']jobTitle[\"'][^>]*>(.*?)</a>", articleHtml)
	relativeLink = findFirstMatch(r"<a[^>]*class=[\"']jobTitle[\"'][^>]*href=[\"']([^\"']+)[\"']", articleHtml)
	link = urljoin(sourceUrl, relativeLink)
	reqId = findFirstMatch(r"ID:\s*<span[^>]*class=[\"']jobContentEM[\"']>(\d+)</span>", articleHtml)
	postedAt = findFirstMatch(r"Posted on\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", articleHtml)
	country = extractFieldValues(articleHtml, "Country")
	city = extractFieldValues(articleHtml, "City")
	experience = extractExperience(articleHtml)
	jobId = generateJobId(title, reqId)

	record = {
		"id": jobId,
		"reqId": reqId,
		"title": title,
		"link": link,
		"postedAt": postedAt,
		"country": country,
		"city": city,
		"experience": experience,
		"state": "open",
	}
	return record


async def collectJobs(page) -> list[dict[str, str]]:
	jobs: list[dict[str, str]] = []

	while True:
		pageHtml = await page.content()
		articles = extractArticles(pageHtml)
		for articleHtml in articles:
			job = parseArticle(articleHtml)
			jobs.append(job)

		nextButton = page.locator('a[aria-label="Next Page"]')
		if await nextButton.count() == 0:
			break

		currentPage = page.locator('td.resultsHeaderPaginator input.sfPaginatorPageSwitch').first
		currentValue = await currentPage.input_value()
		try:
			await nextButton.click()
		except Exception:
			break
		await page.wait_for_function(
			"""(selector, previousValue) => {
				const element = document.querySelector(selector);
				return element && element.value !== previousValue;
			}""",
			'td.resultsHeaderPaginator input.sfPaginatorPageSwitch',
			currentValue,
		)

	return jobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching Systems jobs from %s", url)
	async with async_playwright() as playwright:
		browser = await playwright.chromium.launch(headless=True)
		try:
			page = await browser.new_page(user_agent=userAgent)
			await page.goto(url, wait_until="networkidle", timeout=requestTimeoutSeconds * 1000)
			jobs = await collectJobs(page)
			logger.info("Parsed %d Systems jobs", len(jobs))
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
	if not systemsJsonPath.exists():
		return defaultSnapshot()

	content = systemsJsonPath.read_text(encoding="utf-8")
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
	systemsJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated Systems snapshot at %s", systemsJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update Systems snapshot: %s", error)
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