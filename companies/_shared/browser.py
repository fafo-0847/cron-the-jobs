"""Playwright helpers shared by browser-based scrapers.

Why: on GitHub runners several sites intermittently served Cloudflare challenges,
502/520 origin errors or HTTP2 resets, and scrapers then just timed out on a
selector with no hint of the real cause. These helpers
  * use a normal desktop Chrome user agent (the default "HeadlessChrome" UA is a
    common bot-block trigger),
  * retry transient failures once with a short backoff,
  * turn 4xx/5xx and challenge pages into explicit, readable errors.
"""
from __future__ import annotations

import asyncio
import logging
import re

logger = logging.getLogger(__name__)

desktopUserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
challengeTitlePattern = re.compile(r"Just a moment|Attention Required|Checking your browser", re.I)
transientErrorPattern = re.compile(r"ERR_HTTP2_PROTOCOL_ERROR|ERR_CONNECTION_(?:RESET|CLOSED|REFUSED)|ERR_TIMED_OUT|ERR_EMPTY_RESPONSE|Timeout", re.I)
transientStatuses = {429, 500, 502, 503, 504, 520, 521, 522, 523, 524}


class PageLoadError(Exception):
	pass


async def newPage(browser, userAgent: str = desktopUserAgent):
	context = await browser.new_context(user_agent=userAgent, locale="en-US", viewport={"width": 1366, "height": 900})
	page = await context.new_page()
	return page


async def waitForChallengeToClear(page, timeoutMs: int) -> bool:
	waitedMs = 0
	while waitedMs < timeoutMs:
		title = await page.title()
		if not challengeTitlePattern.search(title or ""):
			return True
		await page.wait_for_timeout(1000)
		waitedMs = waitedMs + 1000
	return False


async def gotoChecked(page, url: str, waitUntil: str = "domcontentloaded", timeoutMs: int = 30000, attempts: int = 2, challengeWaitMs: int = 15000):
	"""page.goto with retries; raises PageLoadError with a readable reason when the page is unusable."""
	lastError: Exception | None = None
	for attempt in range(1, attempts + 1):
		try:
			response = await page.goto(url, wait_until=waitUntil, timeout=timeoutMs)
			status = response.status if response is not None else 0
			title = await page.title()
			isChallenge = challengeTitlePattern.search(title or "") is not None
			if isChallenge:
				cleared = await waitForChallengeToClear(page, challengeWaitMs)
				if cleared:
					return response
				raise PageLoadError(f"Blocked by Cloudflare bot challenge at {url} (title {title!r}, HTTP {status})")
			if status >= 400:
				raise PageLoadError(f"HTTP {status} for {url} (page removed or site down)")
			return response
		except PageLoadError as error:
			lastError = error
			isTransient = any(f"HTTP {code}" in str(error) for code in transientStatuses) or "Cloudflare" in str(error)
			if not isTransient or attempt == attempts:
				raise
		except Exception as error:
			lastError = error
			if not transientErrorPattern.search(str(error)) or attempt == attempts:
				raise
		logger.warning("Retrying %s after transient failure (attempt %d/%d): %s", url, attempt, attempts, str(lastError).splitlines()[0][:200])
		await asyncio.sleep(3 * attempt)
	raise PageLoadError(str(lastError))
