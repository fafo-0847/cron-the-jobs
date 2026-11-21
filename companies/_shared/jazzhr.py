"""JazzHR public boards (<company>.applytojob.com/apply).

Server-rendered list:
  <li class="list-group-item"><h3 class='list-group-item-heading'><a href=".../apply/<code>/<slug>">Title</a></h3>
  <ul class='list-inline list-group-item-text'><li><i class='fa fa-map-marker'></i>Location</li>...</ul></li>
An empty board says "There are no open positions at this time."; an account that left
JazzHR shows "This account is no longer active".
"""
from __future__ import annotations

import html as htmlLib
import re
from typing import Any, Callable

import aiohttp

userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
itemSplitPattern = re.compile(r'<li class=["\']list-group-item["\']>')
linkPattern = re.compile(r'<a href="(?P<href>[^"]+/apply/(?P<code>[A-Za-z0-9]+)/[^"]*)"[^>]*>(?P<title>.*?)</a>', re.S)
metaPattern = re.compile(r"<li><i class=['\"]fa (?P<icon>fa-[a-z-]+)['\"]></i>(?P<text>.*?)</li>", re.S)
noOpeningsPattern = re.compile(r"There are no open positions", re.I)
inactivePattern = re.compile(r"account is no longer active", re.I)


def cleanText(fragment: str) -> str:
	text = htmlLib.unescape(re.sub(r"<[^>]+>", " ", fragment))
	return re.sub(r"\s+", " ", text).replace("\xa0", " ").strip()


def parseBoardHtml(html: str, generateJobId: Callable[[str, str], str]) -> dict[str, Any]:
	if inactivePattern.search(html):
		raise ValueError("JazzHR account is no longer active")
	jobs: list[dict[str, str]] = []
	for chunk in itemSplitPattern.split(html)[1:]:
		linkMatch = linkPattern.search(chunk)
		if linkMatch is None:
			continue
		title = cleanText(linkMatch.group("title"))
		if title == "":
			continue
		fields: dict[str, str] = {}
		for metaMatch in metaPattern.finditer(chunk):
			fields.setdefault(metaMatch.group("icon"), cleanText(metaMatch.group("text")))
		jobs.append({
			"id": generateJobId(title, linkMatch.group("code")),
			"title": title,
			"link": linkMatch.group("href"),
			"location": fields.get("fa-map-marker", ""),
			"department": fields.get("fa-sitemap", ""),
			"jobType": fields.get("fa-clock-o", "") or fields.get("fa-clock", ""),
			"postedAt": "",
			"state": "open",
		})
	confirmedEmpty = len(jobs) == 0 and noOpeningsPattern.search(html) is not None
	if len(jobs) == 0 and not confirmedEmpty:
		raise ValueError("JazzHR board has no job items and no 'no open positions' notice (layout changed)")
	return {"jobs": jobs, "confirmedEmpty": confirmedEmpty}


async def fetchBoardJobs(company: str, generateJobId: Callable[[str, str], str]) -> dict[str, Any]:
	timeout = aiohttp.ClientTimeout(total=30)
	async with aiohttp.ClientSession(headers={"User-Agent": userAgent}, timeout=timeout) as session:
		async with session.get(f"https://{company}.applytojob.com/apply") as response:
			response.raise_for_status()
			html = await response.text()
	return parseBoardHtml(html, generateJobId)
