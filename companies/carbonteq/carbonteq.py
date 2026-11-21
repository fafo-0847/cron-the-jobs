from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import aiohttp

from companies._shared import nextjs


# JazzHR (resumator) account was deactivated in 2026 ("This account is no longer active"),
# so the old API key returns 401. Roles now live on the Next.js careers site, one page
# per track, each with a "#roles" section.
sourceUrl = "https://www.carbonteq.com/careers"
siteUrl = "https://www.carbonteq.com"
trackSlugs = ["engineering", "talent", "product", "design", "ai-ml", "marketing"]
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
requestTimeoutSeconds = 60
carbonteqJsonPath = Path(__file__).with_name("carbonteq.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, jobApiId: str) -> str:
	raw = title + jobApiId
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


# A role card in the flight data: title <p>, location <p>, then the Apply link.
roleCardPattern = re.compile(
	r'"children":"(?P<title>[^"]+)"\}\],\["\$","p",null,\{[^{}]*"children":"(?P<location>[^"]*)"\}\]\]\}\],'
	r'\["\$","\$L\w+",null,\{"href":"(?P<href>/careers/jobs/(?P<jobUuid>[0-9a-fA-F-]+)/apply)"'
)
tagPattern = re.compile(r'\["\$","\$L\w+",null,\{"children":"([^"]+)"\}\]')
noRolesPattern = re.compile(r"No open roles right now", re.I)


def parseTrackPage(html: str, track: str) -> dict[str, Any]:
	"""Returns {"jobs": [...], "empty": bool}; raises if the page has neither roles nor the empty notice."""
	flightText = nextjs.extractFlightText(html)
	matches = list(roleCardPattern.finditer(flightText))
	jobs: list[dict[str, str]] = []
	for index, match in enumerate(matches):
		nextStart = matches[index + 1].start() if index + 1 < len(matches) else min(len(flightText), match.end() + 3000)
		tags = tagPattern.findall(flightText[match.end():nextStart])
		title = match.group("title").strip()
		jobUuid = match.group("jobUuid")
		jobs.append({
			"id": generateJobId(title, jobUuid),
			"title": title,
			"link": siteUrl + match.group("href"),
			"location": match.group("location").strip(),
			"department": track,
			"jobType": ", ".join(tag for tag in tags if tag.lower() != "apply"),
			"postedAt": "",
			"state": "open",
		})
	isEmpty = len(jobs) == 0 and noRolesPattern.search(html) is not None
	if len(jobs) == 0 and not isEmpty:
		raise ValueError(f"carbonteq: no roles and no 'No open roles' notice on {track} page (layout changed)")
	return {"jobs": jobs, "empty": isEmpty}


async def fetchTrackHtml(session: aiohttp.ClientSession, track: str) -> str:
	async with session.get(f"{sourceUrl}/{track}") as response:
		response.raise_for_status()
		return await response.text()


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching CarbonTeq jobs from %s", url)
	allJobs: list[dict[str, str]] = []
	confirmedEmpty = False

	try:
		timeout = aiohttp.ClientTimeout(total=requestTimeoutSeconds)
		async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": userAgent}) as session:
			pages = await asyncio.gather(*(fetchTrackHtml(session, track) for track in trackSlugs))
		seenIds: set[str] = set()
		for track, html in zip(trackSlugs, pages):
			for job in parseTrackPage(html, track)["jobs"]:
				if job["id"] not in seenIds:
					seenIds.add(job["id"])
					allJobs.append(job)
		confirmedEmpty = len(allJobs) == 0
		logger.info("Parsed %d total CarbonTeq jobs", len(allJobs))
	except Exception as error:
		logger.exception("Failed to fetch CarbonTeq jobs: %s", error)
		allJobs = []
		confirmedEmpty = False

	fetchedAt = datetime.now(timezone.utc).isoformat()
	state = {
		"sourceUrl": sourceUrl,
		"fetchedAt": fetchedAt,
		"state": "open",
		"jobs": allJobs,
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
	if not carbonteqJsonPath.exists():
		return defaultSnapshot()

	content = carbonteqJsonPath.read_text(encoding="utf-8")
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
	carbonteqJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated CarbonTeq snapshot at %s", carbonteqJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update CarbonTeq snapshot: %s", error)
		snapshot = buildSnapshot(defaultSnapshot(sourceUrl), existingSnapshot)
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
