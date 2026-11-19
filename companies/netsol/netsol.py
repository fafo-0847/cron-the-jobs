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
from urllib.request import Request, urlopen


sourceUrl = "https://careers.netsoltech.com/openings/"
requestTimeoutSeconds = 30
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
netsolJsonPath = Path(__file__).with_name("netsol.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def fetchHtmlSync(url: str) -> str:
	request = Request(url)
	request.add_header(
		"User-Agent",
		userAgent,
	)

	response = urlopen(request, timeout=requestTimeoutSeconds)
	body = response.read()
	text = body.decode("utf-8", errors="ignore")
	return text


async def fetchHtml(url: str) -> str:
	html = await asyncio.to_thread(fetchHtmlSync, url)
	return html


def findFirstMatch(pattern: str, text: str) -> str:
	match = re.search(pattern, text, flags=re.I | re.S)
	if match is None:
		return ""
	return unescape(match.group(1)).strip()


def generateJobId(title: str, link: str) -> str:
	raw = title + link
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def extractArticles(html: str) -> list[str]:
	articles: list[str] = []
	pattern = re.compile(r"<article\b[^>]*class=[\"'][^\"']*loadmore-item[^\"']*[\"'][^>]*>.*?</article>", re.I | re.S)
	matches = pattern.finditer(html)
	for match in matches:
		articles.append(match.group(0))
	return articles


def parseArticle(articleHtml: str) -> dict[str, str]:
	link = findFirstMatch(r"data-url=[\"']([^\"']+)[\"']", articleHtml)
	if not link:
		link = findFirstMatch(r"<h2[^>]*>\s*<a[^>]*href=[\"']([^\"']+)[\"']", articleHtml)

	title = findFirstMatch(r"<h2[^>]*>\s*<a[^>]*>(.*?)</a>", articleHtml)
	jobType = findFirstMatch(r"<span[^>]*class=[\"'][^\"']*job-type[^\"']*[\"'][^>]*>\s*<a[^>]*>(.*?)</a>", articleHtml)
	location = findFirstMatch(r"<span[^>]*class=[\"'][^\"']*job-location[^\"']*[\"'][^>]*>\s*<a[^>]*>(.*?)</a>", articleHtml)
	postedAt = findFirstMatch(r"<time[^>]*datetime=[\"']([^\"']+)[\"']", articleHtml)
	category = findFirstMatch(r"<span[^>]*class=[\"'][^\"']*job-category[^\"']*[\"'][^>]*>\s*<a[^>]*>(.*?)</a>", articleHtml)
	jobId = generateJobId(title, link)

	record = {
		"id": jobId,
		"title": title,
		"link": link,
		"type": jobType,
		"location": location,
		"postedAt": postedAt,
		"category": category,
		"state": "open",
	}
	return record


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching Netsol jobs from %s", url)
	try:
		html = await fetchHtml(url)
		articles = extractArticles(html)
		jobs: list[dict[str, str]] = []
		for articleHtml in articles:
			job = parseArticle(articleHtml)
			jobs.append(job)
		logger.info("Parsed %d Netsol jobs", len(jobs))
	except Exception as error:
		logger.exception("Failed to fetch Netsol jobs from %s: %s", url, error)
		jobs = []

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
	if not netsolJsonPath.exists():
		return defaultSnapshot()

	content = netsolJsonPath.read_text(encoding="utf-8")
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
	netsolJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated Netsol snapshot at %s", netsolJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update Netsol snapshot: %s", error)
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
