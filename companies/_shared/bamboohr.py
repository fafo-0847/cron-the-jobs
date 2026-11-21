"""BambooHR careers boards (<company>.bamboohr.com/careers).

The embeddable widget that company sites load renders from the public JSON
endpoint <company>.bamboohr.com/careers/list, so we read that directly.
"""
from __future__ import annotations

from typing import Any, Callable

import aiohttp

userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def formatLocation(opening: dict) -> str:
	location = opening.get("location") or {}
	atsLocation = opening.get("atsLocation") or {}
	parts = [location.get("city"), location.get("state")]
	if not any(parts):
		parts = [atsLocation.get("city"), atsLocation.get("state") or atsLocation.get("province"), atsLocation.get("country")]
	text = ", ".join(part for part in parts if part)
	if opening.get("isRemote"):
		text = (text + " (Remote)").strip() if text else "Remote"
	return text


def parseOpening(opening: dict, company: str, generateJobId: Callable[[str, str], str]) -> dict[str, str] | None:
	title = (opening.get("jobOpeningName") or "").replace("\xa0", " ").strip()
	openingId = str(opening.get("id") or "").strip()
	if title == "" or openingId == "":
		return None
	job = {
		"id": generateJobId(title, openingId),
		"title": title,
		"link": f"https://{company}.bamboohr.com/careers/{openingId}",
		"location": formatLocation(opening),
		"department": (opening.get("departmentLabel") or "").strip(),
		"jobType": (opening.get("employmentStatusLabel") or "").strip(),
		"postedAt": "",
		"state": "open",
	}
	return job


async def fetchOpenings(company: str, generateJobId: Callable[[str, str], str]) -> dict[str, Any]:
	"""Returns {"jobs": [...], "confirmedEmpty": bool}. Raises on HTTP/shape errors."""
	url = f"https://{company}.bamboohr.com/careers/list"
	headers = {"User-Agent": userAgent, "Accept": "application/json"}
	timeout = aiohttp.ClientTimeout(total=30)
	async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
		async with session.get(url) as response:
			response.raise_for_status()
			payload = await response.json(content_type=None)
	openings = payload.get("result") if isinstance(payload, dict) else None
	if not isinstance(openings, list):
		raise ValueError(f"unexpected BambooHR payload: {str(payload)[:200]}")
	jobs = [job for job in (parseOpening(opening, company, generateJobId) for opening in openings) if job is not None]
	return {"jobs": jobs, "confirmedEmpty": len(openings) == 0}
