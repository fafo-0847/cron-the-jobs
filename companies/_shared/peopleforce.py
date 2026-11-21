"""PeopleForce career sites (<company>.peopleforce.io/careers).

Server-rendered, paginated with ?page=N and a "Displaying 1 - 10 of N in total"
counter. In 2026 PeopleForce moved to Tailwind classes with a "tw-" prefix, so we
parse by stable anchors (the /careers/v/<id>-<slug> link and Font Awesome icons
that label each meta field) instead of layout classes.
"""
from __future__ import annotations

import html as htmlLib
import math
import re
from typing import Any, Callable
from urllib.parse import urljoin

import aiohttp

userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
maxPages = 30
vacancyLinkPattern = re.compile(r'<a[^>]*href="(?P<href>/careers/v/[^"]+)"[^>]*>(?P<title>.*?)</a>', re.S)
metaItemPattern = re.compile(r'<i class="fas (?P<icon>fa-[a-z-]+)[^"]*"[^>]*></i>(?P<text>[^<]*)', re.S)
tagGap = r"\s*(?:<[^>]+>\s*)*"
totalPattern = re.compile(r"Displaying" + tagGap + r"(?P<first>\d+)\s*-\s*(?P<last>\d+)" + tagGap + r"of" + tagGap + r"(?P<total>\d+)", re.S)
pageLinkPattern = re.compile(r"[?&]page=(\d+)")
noVacanciesPattern = re.compile(r"No (?:open )?(?:vacancies|positions|jobs)", re.I)
iconFields = {
	"fa-briefcase": "department",
	"fa-sitemap": "division",
	"fa-clock": "jobType",
	"fa-map-marker-alt": "location",
	"fa-location-dot": "location",
}


def cleanText(fragment: str) -> str:
	text = htmlLib.unescape(re.sub(r"<[^>]+>", " ", fragment))
	return re.sub(r"\s+", " ", text).replace("\xa0", " ").strip()


def parsePage(html: str, baseUrl: str, generateJobId: Callable[[str, str], str]) -> dict[str, Any]:
	matches = list(vacancyLinkPattern.finditer(html))
	jobs: list[dict[str, str]] = []
	for index, match in enumerate(matches):
		title = cleanText(match.group("title"))
		if title == "":
			continue
		link = urljoin(baseUrl, match.group("href"))
		blockEnd = matches[index + 1].start() if index + 1 < len(matches) else len(html)
		fields: dict[str, str] = {}
		for metaMatch in metaItemPattern.finditer(html[match.end():blockEnd]):
			fieldName = iconFields.get(metaMatch.group("icon"))
			text = cleanText(metaMatch.group("text"))
			if fieldName and text and fieldName not in fields:
				fields[fieldName] = text
		jobs.append({
			"id": generateJobId(title, link),
			"title": title,
			"link": link,
			"location": fields.get("location", ""),
			"department": fields.get("department", ""),
			"jobType": fields.get("jobType", ""),
			"postedAt": "",
			"state": "open",
		})
	totalMatch = totalPattern.search(html)
	total = int(totalMatch.group("total")) if totalMatch else None
	perPage = int(totalMatch.group("last")) - int(totalMatch.group("first")) + 1 if totalMatch else None
	pageNumbers = [int(number) for number in pageLinkPattern.findall(html)]
	maxLinkedPage = max(pageNumbers) if pageNumbers else 1
	return {"jobs": jobs, "total": total, "perPage": perPage, "maxLinkedPage": maxLinkedPage}


async def fetchCareersJobs(careersUrl: str, generateJobId: Callable[[str, str], str]) -> dict[str, Any]:
	"""Returns {"jobs": [...], "confirmedEmpty": bool}. Raises when the page shape is unrecognised."""
	jobs: list[dict[str, str]] = []
	seenLinks: set[str] = set()
	timeout = aiohttp.ClientTimeout(total=45)
	async with aiohttp.ClientSession(headers={"User-Agent": userAgent}, timeout=timeout) as session:
		pageNumber = 1
		lastPage = 1
		firstHtml = ""
		while pageNumber <= lastPage and pageNumber <= maxPages:
			async with session.get(careersUrl, params={"page": str(pageNumber)}) as response:
				response.raise_for_status()
				html = await response.text()
			if pageNumber == 1:
				firstHtml = html
			parsed = parsePage(html, careersUrl, generateJobId)
			if pageNumber == 1:
				hasCounter = parsed["total"] is not None and bool(parsed["perPage"])
				lastPage = max(1, math.ceil(parsed["total"] / parsed["perPage"])) if hasCounter else parsed["maxLinkedPage"]
			for job in parsed["jobs"]:
				if job["link"] not in seenLinks:
					seenLinks.add(job["link"])
					jobs.append(job)
			pageNumber = pageNumber + 1
	if len(jobs) == 0:
		looksEmpty = noVacanciesPattern.search(cleanText(firstHtml)) is not None
		if not looksEmpty:
			raise ValueError("PeopleForce page has no /careers/v/ links and no 'no vacancies' notice (layout changed)")
		return {"jobs": [], "confirmedEmpty": True}
	return {"jobs": jobs, "confirmedEmpty": False}
