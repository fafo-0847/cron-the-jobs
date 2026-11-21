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

import aiohttp

from companies._shared import nextjs


sourceUrl = "https://www.folio3.com/careers"
requestTimeoutSeconds = 60
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
folio3JsonPath = Path(__file__).with_name("folio3.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, link: str) -> str:
	raw = title + link
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


def parseJobsFromHtml(html: str, baseUrl: str) -> list[dict[str, str]]:
	# The Next.js site (Nov 2026 redesign) streams the job list as JSON objects
	# {id, slug, title, division, location, jobType, summary} in its flight data.
	flightText = nextjs.extractFlightText(html)
	rawJobs = nextjs.findJsonObjects(flightText, ["slug", "title", "jobType"])
	jobs: list[dict[str, str]] = []
	seenSlugs: set[str] = set()
	for rawJob in rawJobs:
		title = str(rawJob.get("title") or "").replace("\xa0", " ").strip()
		slug = str(rawJob.get("slug") or "").strip()
		if title == "" or slug == "" or slug in seenSlugs:
			continue
		seenSlugs.add(slug)
		link = urljoin(baseUrl, f"/careers/{slug}")
		record = {
			"id": generateJobId(title, link),
			"title": title,
			"link": link,
			"location": str(rawJob.get("location") or "").strip(),
			"department": str(rawJob.get("division") or "").strip(),
			"jobType": str(rawJob.get("jobType") or "").strip(),
			"postedAt": "",
			"state": "open",
		}
		jobs.append(record)
	return jobs


async def fetchHtml(url: str) -> str:
	headers = {"User-Agent": userAgent, "Accept": "text/html"}
	timeout = aiohttp.ClientTimeout(total=requestTimeoutSeconds)
	async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
		async with session.get(url) as response:
			response.raise_for_status()
			html = await response.text()
	return html


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching Folio3 jobs from %s", url)
	allJobs: list[dict[str, str]] = []

	try:
		html = await fetchHtml(url)
		allJobs = parseJobsFromHtml(html, url)
		if len(allJobs) == 0:
			logger.error("Folio3: no job objects found in page data (layout may have changed)")
		logger.info("Parsed %d total Folio3 jobs", len(allJobs))
	except Exception as error:
		logger.exception("Failed to fetch Folio3 jobs: %s", error)
		allJobs = []

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
	if not folio3JsonPath.exists():
		return defaultSnapshot()

	content = folio3JsonPath.read_text(encoding="utf-8")
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
	folio3JsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated Folio3 snapshot at %s", folio3JsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update Folio3 snapshot: %s", error)
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
