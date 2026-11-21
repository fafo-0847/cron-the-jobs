"""Rippling ATS job boards (ats.rippling.com/<slug>/jobs).

The board is a server-rendered Next.js page: every page embeds its job posts in
<script id="__NEXT_DATA__"> under props.pageProps.dehydratedState.queries[*]
with queryKey [..., "job-posts", ...]. Reading that JSON is far more stable than
the CSS-in-JS markup (class names like css-kcy3vt change on every deploy).
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import aiohttp

userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
requestTimeoutSeconds = 30
maxPages = 20
nextDataPattern = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def generateJobId(title: str, stableId: str) -> str:
	raw = title + stableId if stableId != "" else title
	return hashlib.md5(raw.encode()).hexdigest()


def extractJobPostsData(html: str) -> dict[str, Any]:
	match = nextDataPattern.search(html)
	if match is None:
		raise ValueError("Rippling page has no __NEXT_DATA__ script (blocked or layout changed)")
	nextData = json.loads(match.group(1))
	queries = nextData.get("props", {}).get("pageProps", {}).get("dehydratedState", {}).get("queries", [])
	for query in queries:
		queryKey = query.get("queryKey", [])
		isJobPostsQuery = "job-posts" in queryKey
		if isJobPostsQuery:
			data = query.get("state", {}).get("data") or {}
			if isinstance(data.get("items"), list):
				return data
	raise ValueError("Rippling __NEXT_DATA__ has no job-posts query")


def formatLocations(locations: list[dict]) -> str:
	names: list[str] = []
	for location in locations or []:
		name = (location.get("name") or "").strip()
		if name != "" and name not in names:
			names.append(name)
	return " / ".join(names)


def parseJobItem(item: dict) -> dict[str, str] | None:
	title = (item.get("name") or "").replace("\xa0", " ").strip()
	if title == "":
		return None
	stableId = str(item.get("id") or "").strip()
	link = (item.get("url") or "").strip()
	department = item.get("department") or {}
	departmentName = (department.get("displayName") or department.get("name") or "").strip()
	locations = item.get("locations") or []
	workplaceTypes = sorted({(location.get("workplaceType") or "") for location in locations} - {""})
	job = {
		"id": generateJobId(title, stableId),
		"title": title,
		"link": link,
		"location": formatLocations(locations),
		"department": departmentName,
		"jobType": ", ".join(workplaceTypes),
		"postedAt": "",
		"state": "open",
	}
	return job


def buildPageUrl(boardUrl: str, pageIndex: int) -> str:
	baseUrl = boardUrl.split("?", 1)[0]
	return f"{baseUrl}?page={pageIndex}"


async def fetchBoardJobs(boardUrl: str) -> dict[str, Any]:
	"""Returns {"jobs": [...], "confirmedEmpty": bool}. Raises on HTTP/shape errors."""
	jobs: list[dict[str, str]] = []
	seenIds: set[str] = set()
	totalItems = 0
	headers = {"User-Agent": userAgent, "Accept": "text/html"}
	timeout = aiohttp.ClientTimeout(total=requestTimeoutSeconds)
	async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
		pageIndex = 0
		totalPages = 1
		while pageIndex < totalPages and pageIndex < maxPages:
			async with session.get(buildPageUrl(boardUrl, pageIndex)) as response:
				response.raise_for_status()
				html = await response.text()
			data = extractJobPostsData(html)
			totalPages = int(data.get("totalPages") or 1)
			totalItems = int(data.get("totalItems") or 0)
			for item in data["items"]:
				job = parseJobItem(item)
				if job is not None and job["id"] not in seenIds:
					seenIds.add(job["id"])
					jobs.append(job)
			pageIndex = pageIndex + 1
	confirmedEmpty = len(jobs) == 0 and totalItems == 0
	return {"jobs": jobs, "confirmedEmpty": confirmedEmpty}
