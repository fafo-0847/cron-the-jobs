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


sourceUrl = "https://jobs.dubizzlelabs.com"
requestTimeoutSeconds = 60
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
dubizzleJsonPath = Path(__file__).with_name("dubizzle.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, link: str) -> str:
	raw = title + link
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


# Breezy HR board. Breezy exposes the published positions as JSON at <board>/json,
# which is what the board page itself renders from; the old DOM selectors
# (ul.positions.location li.position) never matched this board's markup.
breezyJsonUrl = sourceUrl + "/json"


def formatBreezyLocation(position: dict) -> str:
	location = position.get("location") or {}
	locationName = (location.get("name") or "").strip()
	if locationName != "":
		return locationName
	city = (location.get("city") or "").strip()
	country = ((location.get("country") or {}).get("name") or "").strip()
	return ", ".join(part for part in [city, country] if part)


def parsePositions(positions: list[dict]) -> list[dict[str, str]]:
	jobs: list[dict[str, str]] = []
	for position in positions:
		title = (position.get("name") or "").strip()
		link = (position.get("url") or "").strip()
		if title == "" or link == "":
			continue
		jobs.append({
			"id": generateJobId(title, link),
			"title": title,
			"link": link,
			"location": formatBreezyLocation(position),
			"department": (position.get("department") or "").strip(),
			"jobType": ((position.get("type") or {}).get("name") or "").strip(),
			"postedAt": position.get("published_date") or "",
			"state": "open",
		})
	return jobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching Dubizzle jobs from %s", breezyJsonUrl)
	jobs: list[dict[str, str]] = []
	confirmedEmpty = False
	try:
		timeout = aiohttp.ClientTimeout(total=requestTimeoutSeconds)
		async with aiohttp.ClientSession(headers={"User-Agent": userAgent}, timeout=timeout) as session:
			async with session.get(breezyJsonUrl) as response:
				response.raise_for_status()
				positions = await response.json(content_type=None)
		if not isinstance(positions, list):
			raise ValueError(f"unexpected Breezy payload: {str(positions)[:200]}")
		jobs = parsePositions(positions)
		confirmedEmpty = len(positions) == 0
		logger.info("Parsed %d total Dubizzle jobs", len(jobs))
	except Exception as error:
		logger.exception("Failed to fetch Dubizzle jobs: %s", error)
		jobs = []

	fetchedAt = datetime.now(timezone.utc).isoformat()
	state = {
		"sourceUrl": url,
		"fetchedAt": fetchedAt,
		"state": "open",
		"jobs": jobs,
		"confirmedEmpty": confirmedEmpty,
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
	if not dubizzleJsonPath.exists():
		return defaultSnapshot()

	content = dubizzleJsonPath.read_text(encoding="utf-8")
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
	dubizzleJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated Dubizzle snapshot at %s", dubizzleJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update Dubizzle snapshot: %s", error)
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
