"""Tell "the board says there are no openings" apart from "the page did not load / layout changed".

Before this, scrapers only waited for a job-card selector, so a board that honestly
listed zero jobs timed out exactly like a broken scrape and the old snapshot was kept forever.
"""
from __future__ import annotations

import re


async def waitForJobsOrEmptyNotice(page, jobSelector: str, emptyNoticePattern: re.Pattern, timeoutMs: int = 30000) -> bool:
	"""Waits until either a job card or the board's empty notice is on the page.

	Returns True when the board shows its empty notice and no job cards; False when job
	cards are present. Raises (Playwright TimeoutError) when neither appears.
	"""
	jobLocator = page.locator(jobSelector)
	emptyLocator = page.get_by_text(emptyNoticePattern)
	await jobLocator.or_(emptyLocator).first.wait_for(state="attached", timeout=timeoutMs)
	jobCount = await jobLocator.count()
	if jobCount > 0:
		return False
	emptyCount = await emptyLocator.count()
	return emptyCount > 0
