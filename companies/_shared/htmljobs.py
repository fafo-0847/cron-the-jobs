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
  emptyPattern   regex; when it appears on the page and no jobs are found the board
                 is confirmed empty (clears old jobs instead of reporting an error)
  maxPages / nextPattern  follow ?page=N style pagination (optional)

Titles fall back from titleSelector -> anchor text -> nearest heading in the card,
skipping generic link texts like "Apply now" or "View details".
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from companies._shared import ats

genericLinkTexts = re.compile(
	r"^(apply|apply now|apply here|view|view job|view details|view role|view position|details|more|read more|learn more|"
	r"see more|know more|explore|open|job details|see details|click here|→|>|»|›)\W*$", re.I)
headingSelector = "h1, h2, h3, h4, h5, h6, strong, b, [class*=title], [class*=Title], [class*=heading]"


def cleanText(text: str) -> str:
	return ats.clean(text)


def stableIdFromLink(link: str) -> str:
	parsed = urlparse(link)
	path = parsed.path.rstrip("/")
	query = f"?{parsed.query}" if parsed.query else ""
	fragment = f"#{parsed.fragment}" if parsed.fragment else ""
	return (path + query + fragment) or link


def nearestCard(element, maxDepth: int = 4):
	current = element
	for _ in range(maxDepth):
		parent = current.parent
		if parent is None or parent.name in ("body", "html", "ul", "ol", "table", "main", "section"):
			break
		current = parent
		if len(current.find_all("a", href=True)) > 3:
			break
	return current


def textOf(scope, selector: str) -> str:
	if not selector or scope is None:
		return ""
	found = scope.select_one(selector)
	return cleanText(found.get_text(" ")) if found is not None else ""


def pickTitle(anchor, card, titleSelector: str) -> str:
	title = textOf(anchor, titleSelector) or textOf(card, titleSelector)
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

	def addJob(title: str, link: str, card) -> None:
		if not title or len(title) > 150:
			return
		jobs.append(ats.makeJob(
			title, stableIdFromLink(link) if link != pageUrl else title, link,
			textOf(card, source.get("locationSelector", "")), textOf(card, source.get("departmentSelector", "")),
			textOf(card, source.get("typeSelector", "")),
		))

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
			addJob(title, link, card)
		return jobs

	if linkPattern is None:
		raise ValueError("html source needs linkPattern or cardSelector")
	for anchor in soup.find_all("a", href=True):
		link = urljoin(pageUrl, anchor["href"].strip())
		if not linkPattern.search(link) or (excludePattern and excludePattern.search(link)):
			continue
		card = nearestCard(anchor)
		addJob(pickTitle(anchor, card, titleSelector), link, card)
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
