"""Checks companies/_shared/emptyboard against a real headless Chromium (skipped when unavailable)."""
import asyncio
import re

import pytest

from companies._shared import emptyboard

playwrightApi = pytest.importorskip("playwright.async_api")


async def runWithContent(html: str, timeoutMs: int = 3000) -> bool:
	async with playwrightApi.async_playwright() as playwright:
		try:
			browser = await playwright.chromium.launch()
		except Exception as error:
			pytest.skip(f"chromium not available: {error}")
		try:
			page = await browser.new_page()
			await page.set_content(html)
			return await emptyboard.waitForJobsOrEmptyNotice(page, "li.job", re.compile("no open positions", re.I), timeoutMs)
		finally:
			await browser.close()


def test_empty_notice_detected():
	assert asyncio.run(runWithContent("<p>There are no open positions at this time.</p>")) is True


def test_jobs_present():
	assert asyncio.run(runWithContent("<ul><li class='job'>Engineer</li></ul><p>no open positions in Berlin</p>")) is False


def test_neither_present_times_out():
	with pytest.raises(Exception):
		asyncio.run(runWithContent("<p>loading…</p>", timeoutMs=500))
