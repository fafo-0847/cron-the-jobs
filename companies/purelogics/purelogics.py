from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp


sourceUrl = "https://hiring.purelogics.com/careers"
requestTimeoutSeconds = 60
userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
purelogicsJsonPath = Path(__file__).with_name("purelogics.json")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def generateJobId(title: str, link: str) -> str:
	raw = title + link
	jobId = hashlib.md5(raw.encode()).hexdigest()
	return jobId


# Nov 2026: purelogics.com/careers/ is a 404; the site links to a new in-house hiring
# portal (hiring.purelogics.com/careers) backed by a public JSON API.
apiUrl = "https://hiring.purelogics.com/api/public/tenant/purelogics/jobs"
jobLinkTemplate = "https://hiring.purelogics.com/careers/job/{jobId}"
apiPageSize = 50
maxPages = 20


def formatEnum(value: str) -> str:
	return (value or "").replace("_", " ").title()


def parseApiJobs(items: list[dict]) -> list[dict[str, str]]:
	jobs: list[dict[str, str]] = []
	for item in items:
		title = (item.get("title") or "").strip()
		apiJobId = str(item.get("id") or "").strip()
		if title == "" or apiJobId == "":
			continue
		link = jobLinkTemplate.format(jobId=apiJobId)
		jobTypeParts = [formatEnum(item.get("job_type") or ""), formatEnum(item.get("working_model") or "")]
		jobs.append({
			"id": generateJobId(title, link),
			"title": title,
			"link": link,
			"location": (item.get("location") or "").strip(),
			"department": (item.get("department_name") or "").strip(),
			"jobType": ", ".join(part for part in jobTypeParts if part),
			"postedAt": item.get("posted_at") or "",
			"state": "open",
		})
	return jobs


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	logger.info("Fetching PureLogics jobs from %s", apiUrl)
	allJobs: list[dict[str, str]] = []
	confirmedEmpty = False
	try:
		timeout = aiohttp.ClientTimeout(total=requestTimeoutSeconds)
		async with aiohttp.ClientSession(headers={"User-Agent": userAgent, "Accept": "application/json"}, timeout=timeout) as session:
			pageNumber = 1
			totalPages = 1
			totalCount = 0
			while pageNumber <= totalPages and pageNumber <= maxPages:
				async with session.get(apiUrl, params={"page": str(pageNumber), "page_size": str(apiPageSize)}) as response:
					response.raise_for_status()
					payload = await response.json(content_type=None)
				items = payload.get("items")
				if not isinstance(items, list):
					raise ValueError(f"unexpected PureLogics API payload: {str(payload)[:200]}")
				totalPages = int(payload.get("total_pages") or 1)
				totalCount = int(payload.get("total_count") or 0)
				allJobs.extend(parseApiJobs(items))
				pageNumber = pageNumber + 1
		confirmedEmpty = len(allJobs) == 0 and totalCount == 0
		logger.info("Parsed %d total PureLogics jobs", len(allJobs))
	except Exception as error:
		logger.exception("Failed to fetch PureLogics jobs: %s", error)
		allJobs = []
		confirmedEmpty = False

	fetchedAt = datetime.now(timezone.utc).isoformat()
	state = {
		"sourceUrl": url,
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
	if not purelogicsJsonPath.exists():
		return defaultSnapshot()

	content = purelogicsJsonPath.read_text(encoding="utf-8")
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
	purelogicsJsonPath.write_text(output + "\n", encoding="utf-8")


async def updateSnapshot(url: str = sourceUrl) -> dict[str, Any]:
	existingSnapshot = loadExistingSnapshot()
	try:
		state = await fetchState(url)
		snapshot = buildSnapshot(state, existingSnapshot)
		await asyncio.to_thread(writeSnapshot, snapshot)
		logger.info("Updated PureLogics snapshot at %s", purelogicsJsonPath)
		return snapshot
	except Exception as error:
		logger.exception("Failed to update PureLogics snapshot: %s", error)
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
