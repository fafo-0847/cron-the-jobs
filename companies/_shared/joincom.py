"""JOIN (join.com/companies/<slug>) job boards.

The board page is server-rendered Next.js; props.pageProps.pageData.jobs holds
{"items": [...], "pagination": {"page", "pageCount", "total", ...}}.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

import aiohttp

userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
maxPages = 20
nextDataPattern = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def extractJobsData(html: str) -> dict[str, Any]:
	match = nextDataPattern.search(html)
	if match is None:
		raise ValueError("join.com page has no __NEXT_DATA__ (blocked or layout changed)")
	pageData = json.loads(match.group(1)).get("props", {}).get("pageProps", {}).get("pageData", {})
	jobsData = pageData.get("jobs")
	if not isinstance(jobsData, dict) or not isinstance(jobsData.get("items"), list):
		raise ValueError("join.com __NEXT_DATA__ has no pageData.jobs.items")
	return jobsData


def parseItem(item: dict, companySlug: str, generateJobId: Callable[[str, str], str]) -> dict[str, str] | None:
	title = (item.get("title") or "").replace("\xa0", " ").strip()
	idParam = str(item.get("idParam") or "").strip()
	if title == "" or idParam == "":
		return None
	numericId = idParam.split("-")[0]
	stableId = numericId if numericId.isdigit() else idParam
	city = item.get("city") or {}
	locationParts = [part for part in [city.get("cityName"), city.get("countryName")] if part]
	employmentType = (item.get("employmentType") or {}).get("name") or ""
	workplaceType = item.get("workplaceType") or ""
	jobTypeParts = [part for part in [employmentType, workplaceType] if part]
	job = {
		"id": generateJobId(title, stableId),
		"title": title,
		"link": f"https://join.com/companies/{companySlug}/{idParam}",
		"location": ", ".join(locationParts),
		"department": (item.get("category") or {}).get("name") or "",
		"jobType": ", ".join(jobTypeParts),
		"postedAt": item.get("createdAt") or "",
		"state": "open",
	}
	return job


async def fetchBoardJobs(companySlug: str, generateJobId: Callable[[str, str], str]) -> dict[str, Any]:
	"""Returns {"jobs": [...], "confirmedEmpty": bool}. Raises on HTTP/shape errors."""
	jobs: list[dict[str, str]] = []
	total = 0
	timeout = aiohttp.ClientTimeout(total=30)
	async with aiohttp.ClientSession(headers={"User-Agent": userAgent}, timeout=timeout) as session:
		page = 1
		pageCount = 1
		while page <= pageCount and page <= maxPages:
			async with session.get(f"https://join.com/companies/{companySlug}", params={"page": str(page)}) as response:
				response.raise_for_status()
				html = await response.text()
			jobsData = extractJobsData(html)
			pagination = jobsData.get("pagination") or {}
			pageCount = int(pagination.get("pageCount") or 0)
			total = int(pagination.get("total") or 0)
			for item in jobsData["items"]:
				job = parseItem(item, companySlug, generateJobId)
				if job is not None:
					jobs.append(job)
			page = page + 1
	confirmedEmpty = len(jobs) == 0 and total == 0
	return {"jobs": jobs, "confirmedEmpty": confirmedEmpty}
