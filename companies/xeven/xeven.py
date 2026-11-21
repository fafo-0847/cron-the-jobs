from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import html as htmlLib
import re

import aiohttp


sourceUrl = "https://www.xevensolutions.com/careers"
requestTimeoutSeconds = 60
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
xevenJsonPath = Path(__file__).with_name("xeven.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, jobType: str, location: str) -> str:
	raw = title + jobType + location
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


# 2026 redesign: roles are <div class="role-row"><h4>Title</h4><span class="meta">Team</span>
# <span class="meta">Location</span></div> inside <div class="roles">, server-rendered, no per-role links.
roleRowPattern = re.compile(r'<div class="role-row">(.*?)</div>', re.S)
roleTitlePattern = re.compile(r"<h4[^>]*>(.*?)</h4>", re.S)
roleMetaPattern = re.compile(r'<span class="meta">(.*?)</span>', re.S)


def cleanText(fragment: str) -> str:
	text = htmlLib.unescape(re.sub(r"<[^>]+>", " ", fragment))
	return re.sub(r"\s+", " ", text).strip()


def parseRolesHtml(html: str, url: str = sourceUrl) -> list[dict[str, str]]:
	jobs: list[dict[str, str]] = []
	for rowMatch in roleRowPattern.finditer(html):
		rowHtml = rowMatch.group(1)
		titleMatch = roleTitlePattern.search(rowHtml)
		title = cleanText(titleMatch.group(1)) if titleMatch else ""
		if title == "":
			continue
		metas = [cleanText(text) for text in roleMetaPattern.findall(rowHtml)]
		department = metas[0] if len(metas) > 0 else ""
		location = metas[1] if len(metas) > 1 else ""
		jobs.append({
			"id": generateJobId(title, department, location),
			"title": title,
			"link": url,
			"location": location,
			"department": department,
			"jobType": "",
			"postedAt": "",
			"state": "open",
		})
	return jobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching Xeven jobs from %s", url)
	allJobs: list[dict[str, str]] = []
	try:
		timeout = aiohttp.ClientTimeout(total=requestTimeoutSeconds)
		async with aiohttp.ClientSession(headers={"User-Agent": userAgent}, timeout=timeout) as session:
			async with session.get(url) as response:
				response.raise_for_status()
				html = await response.text()
		allJobs = parseRolesHtml(html, url)
		if len(allJobs) == 0:
			logger.error("Xeven: no role rows found on careers page (layout changed?)")
		logger.info("Parsed %d total Xeven jobs", len(allJobs))
	except Exception as error:
		logger.exception("Failed to fetch Xeven jobs: %s", error)
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
	if not xevenJsonPath.exists():
		return defaultSnapshot()

	content = xevenJsonPath.read_text(encoding="utf-8")
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
	xevenJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated Xeven snapshot at %s", xevenJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update Xeven snapshot: %s", error)
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