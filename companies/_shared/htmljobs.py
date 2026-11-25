"""Configurable scraper for job lists on a company's own careers page.

Source config keys (type "html"):
  url            careers page URL (required)
  render         True to load the page in headless Chromium (JS-rendered pages)
  waitFor        CSS selector to wait for when rendering (optional)
  linkPattern    regex an <a href> (absolute) must match to count as a job link
  excludePattern regex for hrefs to skip (e.g. category pages)
  cardSelector   CSS selector for one job card; used instead of / together with links
  titleSelector  CSS selector for the title inside a card or link (optional)
  locationSelector, typeSelector, departmentSelector  optional, inside the card
  requireJobWord True to keep only titles containing a job word (Engineer, Intern, Manager, ...)
  titleFromParam take the title from a link query parameter (e.g. "subject" of a mailto link)
  titleStripPattern regex removed from titles (e.g. " – \\[Your Name\\]")
  jsonLd         True to read schema.org JobPosting / ItemList JSON-LD instead of links
  emptyPattern   regex; when it appears on the page and no jobs are found the board
                 is confirmed empty (clears old jobs instead of reporting an error)
  maxPages / nextPattern  follow ?page=N style pagination (optional)

Titles fall back from titleSelector -> anchor text -> nearest heading in the card,
skipping generic link texts like "Apply now" or "View details".
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from companies._shared import ats

genericLinkTexts = re.compile(
	r"^(apply|apply now|apply here|apply today|view|view (?:job |the )?(?:job|jobs|details?|description|role|position|opening)|details?|more|more info|read more|learn more|"
	r"see more|know more|explore|open|job details?|job description|see details?|click here|show more|apply on .{1,40}|apply for (?:this|the) (?:role|job|position)|→|>|»|›)\W*$", re.I)
jobTitleWords = re.compile(
	r"\b(engineer|developer|manager|executive|intern(ship)?s?|designer|analyst|specialist|lead|officer|consultant|associate|architect|"
	r"representative|writer|scientist|accountant|coordinator|tester|s?qa|devops|marketer|recruiter|administrator|technician|trainee|"
	r"director|head|strategist|programmer|editor|agent|assistant|operator|supervisor|advisor|researcher|creator|videographer|animator|"
	r"teacher|expert|generalist|receptionist|admin|controller|auditor|counsel|partner|owner|scrum master|evangelist|artist|illustrator|"
	r"photographer|copywriter|sdr|bdr|bde|hr|cfo|cto|ceo|staff|chief|fellow|apprentice|graduate|nurse|doctor|pharmacist|driver|clerk)\b", re.I)
headingSelector = "h1, h2, h3, h4, h5, h6, strong, b, [class*=title], [class*=Title], [class*=heading]"


def cleanText(text: str) -> str:
	return ats.clean(text)


def stableIdFromLink(link: str) -> str:
	parsed = urlparse(link)
	path = parsed.path.rstrip("/")
	query = f"?{parsed.query}" if parsed.query else ""
	fragment = f"#{parsed.fragment}" if parsed.fragment else ""
	return (path + query + fragment) or link


def nearestCard(element, maxDepth: int = 4, isJobLink=None):
	"""Climb from a job link to its card, stopping before a block that holds another job's link."""
	ownHref = element.get("href", "")
	current = element
	for _ in range(maxDepth):
		parent = current.parent
		if parent is None or parent.name in ("body", "html", "ul", "ol", "table", "main", "section"):
			break
		otherJobLinks = [anchor for anchor in parent.find_all("a", href=True) if anchor.get("href") != ownHref and (isJobLink is None or isJobLink(anchor))]
		if (isJobLink is not None and otherJobLinks) or len(parent.find_all("a", href=True)) > 3:
			break
		current = parent
	return current


def parseJsonLd(soup, pageUrl: str) -> list[dict[str, str]]:
	"""Jobs from schema.org JSON-LD: JobPosting objects or an ItemList of postings."""
	jobs: list[dict[str, str]] = []

	def walk(node) -> None:
		if isinstance(node, list):
			for item in node:
				walk(item)
			return
		if not isinstance(node, dict):
			return
		nodeType = node.get("@type")
		types = nodeType if isinstance(nodeType, list) else [nodeType]
		if "JobPosting" in types:
			location = node.get("jobLocation") or {}
			location = location[0] if isinstance(location, list) and location else location
			address = location.get("address", {}) if isinstance(location, dict) else {}
			locationText = ats.joinParts([address.get("addressLocality"), address.get("addressCountry")]) if isinstance(address, dict) else ""
			link = urljoin(pageUrl, node.get("url") or pageUrl)
			employmentType = node.get("employmentType")
			jobs.append(ats.makeJob(node.get("title") or node.get("name"), stableIdFromLink(link), link, locationText,
				"", ", ".join(employmentType) if isinstance(employmentType, list) else employmentType or "", node.get("datePosted") or ""))
		elif "ItemList" in types and node.get("itemListElement"):
			for element in node["itemListElement"]:
				item = element.get("item", element) if isinstance(element, dict) else {}
				if isinstance(item, dict) and item.get("@type") == "JobPosting":
					walk(item)
				elif isinstance(item, dict) and (item.get("name") and (element.get("url") or item.get("url"))):
					link = urljoin(pageUrl, element.get("url") or item.get("url"))
					jobs.append(ats.makeJob(item.get("name"), stableIdFromLink(link), link))
		for key in ("@graph", "mainEntity", "itemListElement"):
			if key in node and key != "itemListElement":
				walk(node[key])

	for script in soup.find_all("script", type="application/ld+json"):
		try:
			walk(json.loads(script.string or script.get_text() or "null"))
		except (json.JSONDecodeError, TypeError):
			continue
	return jobs


def textOf(scope, selector: str) -> str:
	if not selector or scope is None:
		return ""
	found = scope.select_one(selector)
	return cleanText(found.get_text(" ")) if found is not None else ""


def pickTitle(anchor, card, titleSelector: str) -> str:
	title = textOf(anchor, titleSelector) or (textOf(card, titleSelector) if not anchor.select_one(titleSelector or "x-none") else "")
	if title:
		return title
	for heading in anchor.select(headingSelector):
		text = cleanText(heading.get_text(" "))
		if text and not genericLinkTexts.match(text):
			return text
	anchorText = cleanText(anchor.get_text(" "))
	if anchorText and not genericLinkTexts.match(anchorText) and len(anchorText) <= 120:
		return anchorText
	if card is not None:
		for heading in card.select(headingSelector):
			text = cleanText(heading.get_text(" "))
			if text and not genericLinkTexts.match(text):
				return text
	return ""


def parseJobs(html: str, source: dict, pageUrl: str) -> list[dict[str, str]]:
	soup = BeautifulSoup(html, "html.parser")
	linkPattern = re.compile(source["linkPattern"], re.I) if source.get("linkPattern") else None
	excludePattern = re.compile(source["excludePattern"], re.I) if source.get("excludePattern") else None
	titleSelector = source.get("titleSelector", "")
	jobs: list[dict[str, str]] = []

	seenLinks: set[str] = set()

	def fieldText(scopes: list, selector: str) -> str:
		for scope in scopes:
			text = textOf(scope, selector)
			if text:
				return text
		return ""

	def addJob(title: str, link: str, card, anchor=None) -> None:
		if not title or len(title) > 150 or genericLinkTexts.match(title) or "@" in title or title.lower().startswith("http"):
			return
		if source.get("requireJobWord") and not jobTitleWords.search(title):
			return
		if link != pageUrl:
			if link in seenLinks:
				return
			seenLinks.add(link)
		scopes = [scope for scope in (anchor, card) if scope is not None]
		jobs.append(ats.makeJob(
			title, stableIdFromLink(link) if link != pageUrl else title, link,
			fieldText(scopes, source.get("locationSelector", "")), fieldText(scopes, source.get("departmentSelector", "")),
			fieldText(scopes, source.get("typeSelector", "")),
		))

	if source.get("jsonLd"):
		return parseJsonLd(soup, pageUrl)

	if source.get("cardSelector"):
		for card in soup.select(source["cardSelector"]):
			anchor = card if card.name == "a" and card.get("href") else card.find("a", href=True)
			link = urljoin(pageUrl, anchor["href"]) if anchor is not None else pageUrl
			if linkPattern and anchor is not None and not linkPattern.search(link):
				link = pageUrl
			title = textOf(card, titleSelector) or (pickTitle(anchor, card, "") if anchor is not None else "")
			if not title:
				for heading in card.select(headingSelector):
					title = cleanText(heading.get_text(" "))
					if title:
						break
			if not title:
				title = cleanText(card.get_text(" "))
			if source.get("titleStripPattern"):
				title = cleanText(re.sub(source["titleStripPattern"], "", title))
			addJob(title, link, card, anchor)
		return jobs

	if linkPattern is None:
		raise ValueError("html source needs linkPattern or cardSelector")
	def isJobLink(anchor) -> bool:
		candidate = urljoin(pageUrl, anchor["href"].strip())
		return bool(linkPattern.search(candidate)) and not (excludePattern and excludePattern.search(candidate))

	for anchor in soup.find_all("a", href=True):
		if not isJobLink(anchor):
			continue
		link = urljoin(pageUrl, anchor["href"].strip())
		card = nearestCard(anchor, isJobLink=isJobLink)
		title = pickTitle(anchor, card, titleSelector)
		if source.get("titleFromParam"):
			# e.g. mailto:careers@x.com?subject=Equity%20Research%20Analyst
			paramValues = parse_qs(urlparse(link).query).get(source["titleFromParam"], [])
			title = cleanText(paramValues[0]) if paramValues else title
		if source.get("titleStripPattern"):
			title = cleanText(re.sub(source["titleStripPattern"], "", title))
		addJob(title, link, card, anchor)
	return jobs


async def fetchPageHttp(url: str) -> str:
	headers = {"User-Agent": ats.userAgent, "Accept": "text/html,application/xhtml+xml"}
	async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=45)) as session:
		async with session.get(url) as response:
			response.raise_for_status()
			return await response.text()


async def fetchPagesRendered(urls: list[str], waitFor: str) -> list[str]:
	from playwright.async_api import async_playwright

	from companies._shared import browser as sharedBrowser

	pages: list[str] = []
	async with async_playwright() as playwright:
		browserInstance = await playwright.chromium.launch()
		try:
			page = await sharedBrowser.newPage(browserInstance)
			for url in urls:
				await sharedBrowser.gotoChecked(page, url, waitUntil="domcontentloaded", timeoutMs=45000)
				if waitFor:
					try:
						await page.wait_for_selector(waitFor, state="attached", timeout=20000)
					except Exception:
						pass
				try:
					await page.wait_for_load_state("networkidle", timeout=15000)
				except Exception:
					pass
				await page.wait_for_timeout(1500)
				pages.append(await page.content())
		finally:
			await browserInstance.close()
	return pages


def pageUrls(source: dict) -> list[str]:
	urls = [source["url"]]
	for pageNumber in range(2, int(source.get("maxPages", 1)) + 1):
		urls.append(source["pageUrlTemplate"].format(page=pageNumber))
	return urls


async def fetchHtmlJobs(source: dict) -> dict[str, Any]:
	urls = pageUrls(source)
	if source.get("render"):
		htmlPages = await fetchPagesRendered(urls, source.get("waitFor", ""))
	else:
		htmlPages = [await fetchPageHttp(url) for url in urls]
	jobs: list[dict[str, str]] = []
	for url, html in zip(urls, htmlPages):
		pageJobs = parseJobs(html, source, url)
		jobs.extend(pageJobs)
		if url != urls[0] and len(pageJobs) == 0:
			break
	emptyPattern = source.get("emptyPattern")
	pageSaysEmpty = bool(emptyPattern) and re.search(emptyPattern, BeautifulSoup(htmlPages[0], "html.parser").get_text(" "), re.I) is not None
	return ats.result(jobs, pageSaysEmpty)
