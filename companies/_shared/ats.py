"""Fetchers for job sources, all returning the same normalized shape.

Every fetcher returns {"jobs": [...], "confirmedEmpty": bool} and raises on HTTP
or payload-shape errors (so the run is reported, never silently empty).
Each job: id, title, link, location, department, jobType, postedAt, state.
Job ids are md5(title + stableId) with the source's own job id as stableId,
which matches how the hand-written scrapers in this repo build ids.

Source config (a dict) picks the fetcher via "type":
  greenhouse {slug} | lever {slug, region?} | ashby {slug} | workable {slug}
  recruitee {slug} | smartrecruiters {slug} | breezy {url} | personio {slug}
  workday {url}  (the public myworkdayjobs.com site URL, e.g.
                  https://x.wd3.myworkdayjobs.com/en-US/External)
  pinpoint {slug} | manatal {slug} (careers-page.com/<slug>) | teamtailor {url}
  jsonapi {url, itemsPath, fields: {title, id, location, department, jobType, postedAt}, linkTemplate}
          a company's own JSON endpoint; linkTemplate is formatted with the item's fields, e.g. "https://x.com/jobs/{slug}"
  zohorecruit {url}  (career site, e.g. https://acme.zohorecruit.com/jobs/Careers; idFrom "link" keeps md5(title+link) ids)
  bamboohr {slug} | jazzhr {slug} | rippling {url} | joincom {slug} | peopleforce {url}
  html {url, ...}  see companies/_shared/htmljobs.py
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import aiohttp

userAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
requestTimeoutSeconds = 30
maxPages = 30


def generateJobId(title: str, stableId: str) -> str:
	raw = title + stableId if stableId != "" else title
	return hashlib.md5(raw.encode()).hexdigest()


def clean(value: Any) -> str:
	if value is None:
		return ""
	text = str(value).replace("\xa0", " ")
	return re.sub(r"\s+", " ", text).strip()


def joinParts(parts: list, separator: str = ", ") -> str:
	kept: list[str] = []
	for part in parts:
		text = clean(part)
		if text != "" and text not in kept:
			kept.append(text)
	return separator.join(kept)


def makeJob(title: str, stableId: str, link: str, location: str = "", department: str = "", jobType: str = "", postedAt: str = "") -> dict[str, str]:
	title = clean(title)
	return {
		"id": generateJobId(title, clean(stableId)),
		"title": title,
		"link": clean(link),
		"location": clean(location),
		"department": clean(department),
		"jobType": clean(jobType),
		"postedAt": clean(postedAt),
		"state": "open",
	}


def result(jobs: list[dict], sourceSaysEmpty: bool) -> dict[str, Any]:
	uniqueJobs: list[dict] = []
	seenIds: set[str] = set()
	for job in jobs:
		if job["title"] == "" or job["id"] in seenIds:
			continue
		seenIds.add(job["id"])
		uniqueJobs.append(job)
	return {"jobs": uniqueJobs, "confirmedEmpty": sourceSaysEmpty and len(uniqueJobs) == 0}


def newSession(extraHeaders: dict | None = None) -> aiohttp.ClientSession:
	headers = {"User-Agent": userAgent, "Accept": "application/json, text/html;q=0.9, */*;q=0.8"}
	headers.update(extraHeaders or {})
	return aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=requestTimeoutSeconds))


async def requestJson(session: aiohttp.ClientSession, url: str, method: str = "GET", payload: Any = None, retries: int = 2) -> Any:
	for attempt in range(retries + 1):
		async with session.request(method, url, json=payload) as response:
			isRateLimited = response.status == 429 or response.status >= 500
			if isRateLimited and attempt < retries:
				retryAfter = response.headers.get("Retry-After", "")
				waitSeconds = min(int(retryAfter), 60) if retryAfter.isdigit() else 10 * (attempt + 1)
				await asyncio.sleep(waitSeconds)
				continue
			response.raise_for_status()
			text = await response.text()
		try:
			return json.loads(text)
		except json.JSONDecodeError as error:
			raise ValueError(f"non-JSON response from {url}: {text[:150]!r}") from error
	raise RuntimeError(f"gave up on {url}")


def requireList(value: Any, what: str) -> list:
	if not isinstance(value, list):
		raise ValueError(f"unexpected {what} payload: {str(value)[:200]}")
	return value


async def fetchGreenhouse(source: dict) -> dict[str, Any]:
	slug = source["slug"]
	async with newSession() as session:
		payload = await requestJson(session, f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
	rawJobs = requireList(payload.get("jobs") if isinstance(payload, dict) else None, "Greenhouse")
	jobs = []
	for rawJob in rawJobs:
		departments = rawJob.get("departments") or []
		jobs.append(makeJob(
			rawJob.get("title"), str(rawJob.get("id") or ""), rawJob.get("absolute_url"),
			(rawJob.get("location") or {}).get("name"),
			departments[0].get("name") if departments else "",
			"", rawJob.get("first_published") or rawJob.get("updated_at") or "",
		))
	return result(jobs, len(rawJobs) == 0)


async def fetchLever(source: dict) -> dict[str, Any]:
	host = "api.eu.lever.co" if source.get("region") == "eu" else "api.lever.co"
	async with newSession() as session:
		postings = requireList(await requestJson(session, f"https://{host}/v0/postings/{source['slug']}?mode=json"), "Lever")
	jobs = []
	for posting in postings:
		categories = posting.get("categories") or {}
		createdAt = posting.get("createdAt")
		postedAt = datetime.fromtimestamp(createdAt / 1000, timezone.utc).date().isoformat() if isinstance(createdAt, (int, float)) else ""
		jobs.append(makeJob(
			posting.get("text"), posting.get("id") or "", posting.get("hostedUrl"),
			categories.get("location") or joinParts(categories.get("allLocations") or []),
			categories.get("team") or categories.get("department"), categories.get("commitment"), postedAt,
		))
	return result(jobs, len(postings) == 0)


async def fetchAshby(source: dict) -> dict[str, Any]:
	async with newSession() as session:
		payload = await requestJson(session, f"https://api.ashbyhq.com/posting-api/job-board/{source['slug']}")
	rawJobs = requireList(payload.get("jobs") if isinstance(payload, dict) else None, "Ashby")
	jobs = [makeJob(
		rawJob.get("title"), rawJob.get("id") or "", rawJob.get("jobUrl") or rawJob.get("applyUrl"),
		rawJob.get("location"), rawJob.get("department") or rawJob.get("team"),
		joinParts([rawJob.get("employmentType"), rawJob.get("workplaceType")]), rawJob.get("publishedAt"),
	) for rawJob in rawJobs if rawJob.get("isListed", True)]
	return result(jobs, len(rawJobs) == 0)


# Workable rate-limits per IP (HTTP 429) when many boards are hit back to back, so calls
# are spaced out and 429s are retried with the server's Retry-After.
workableMinIntervalSeconds = 4.0
workableLock = asyncio.Lock()
workableLastCall = 0.0


async def fetchWorkable(source: dict) -> dict[str, Any]:
	global workableLastCall
	async with workableLock:
		waitSeconds = workableMinIntervalSeconds - (time.monotonic() - workableLastCall)
		if waitSeconds > 0:
			await asyncio.sleep(waitSeconds)
		try:
			async with newSession() as session:
				payload = await requestJson(session, f"https://apply.workable.com/api/v1/widget/accounts/{source['slug']}", retries=3)
		finally:
			workableLastCall = time.monotonic()
	rawJobs = requireList(payload.get("jobs") if isinstance(payload, dict) else None, "Workable")
	jobs = []
	for rawJob in rawJobs:
		locations = rawJob.get("locations") or []
		if locations:
			location = " / ".join(joinParts([item.get("city"), item.get("region"), item.get("country")]) for item in locations)
		else:
			location = joinParts([rawJob.get("city"), rawJob.get("state"), rawJob.get("country")])
		if rawJob.get("telecommuting"):
			location = joinParts([location, "Remote"])
		jobs.append(makeJob(
			rawJob.get("title"), rawJob.get("shortcode") or "", rawJob.get("shortlink") or rawJob.get("url") or rawJob.get("application_url"),
			location, rawJob.get("department"), rawJob.get("employment_type"), rawJob.get("published_on") or rawJob.get("created_at"),
		))
	return result(jobs, len(rawJobs) == 0)


async def fetchRecruitee(source: dict) -> dict[str, Any]:
	async with newSession() as session:
		payload = await requestJson(session, f"https://{source['slug']}.recruitee.com/api/offers/")
	offers = requireList(payload.get("offers") if isinstance(payload, dict) else None, "Recruitee")
	jobs = [makeJob(
		offer.get("title"), str(offer.get("id") or ""), offer.get("careers_url") or offer.get("url"),
		offer.get("location") or joinParts([offer.get("city"), offer.get("country")]), offer.get("department"),
		offer.get("employment_type_code"), offer.get("published_at"),
	) for offer in offers]
	return result(jobs, len(offers) == 0)


async def fetchSmartRecruiters(source: dict) -> dict[str, Any]:
	slug = source["slug"]
	jobs = []
	offset = 0
	total = 0
	async with newSession() as session:
		for _ in range(maxPages):
			payload = await requestJson(session, f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={offset}")
			postings = requireList(payload.get("content") if isinstance(payload, dict) else None, "SmartRecruiters")
			total = int(payload.get("totalFound") or 0)
			for posting in postings:
				location = posting.get("location") or {}
				jobs.append(makeJob(
					posting.get("name"), posting.get("id") or "", f"https://jobs.smartrecruiters.com/{slug}/{posting.get('id')}",
					location.get("fullLocation") or joinParts([location.get("city"), location.get("country")]),
					(posting.get("department") or {}).get("label"), (posting.get("typeOfEmployment") or {}).get("label"),
					posting.get("releasedDate"),
				))
			offset = offset + len(postings)
			if len(postings) == 0 or offset >= total:
				break
	return result(jobs, total == 0)


async def fetchBreezy(source: dict) -> dict[str, Any]:
	baseUrl = source["url"].rstrip("/")
	async with newSession() as session:
		positions = requireList(await requestJson(session, baseUrl + "/json"), "Breezy")
	jobs = []
	for position in positions:
		location = position.get("location") or {}
		friendlyId = clean(position.get("friendly_id") or "")
		jobs.append(makeJob(
			position.get("name"), clean(position.get("id")) or friendlyId.split("-")[0], position.get("url"),
			location.get("name") or joinParts([location.get("city"), (location.get("country") or {}).get("name")]),
			position.get("department"), (position.get("type") or {}).get("name"), position.get("published_date"),
		))
	return result(jobs, len(positions) == 0)


async def fetchPersonio(source: dict) -> dict[str, Any]:
	slug = source["slug"]
	domain = source.get("domain", "de")
	async with newSession({"Accept": "application/xml"}) as session:
		async with session.get(f"https://{slug}.jobs.personio.{domain}/xml") as response:
			response.raise_for_status()
			text = await response.text()
	root = ElementTree.fromstring(text)
	positions = root.findall("position")
	jobs = []
	for position in positions:
		positionId = clean(position.findtext("id"))
		jobs.append(makeJob(
			position.findtext("name"), positionId, f"https://{slug}.jobs.personio.{domain}/job/{positionId}",
			position.findtext("office"), position.findtext("department"),
			joinParts([position.findtext("employmentType"), position.findtext("schedule")]), position.findtext("createdAt"),
		))
	return result(jobs, len(positions) == 0)


def parseWorkdaySiteUrl(siteUrl: str) -> tuple[str, str, str]:
	"""https://acme.wd3.myworkdayjobs.com/en-US/External -> (origin, tenant 'acme', site 'External')."""
	parsed = urlparse(siteUrl)
	tenant = parsed.hostname.split(".")[0]
	pathParts = [part for part in parsed.path.split("/") if part]
	if pathParts and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", pathParts[0]):
		pathParts = pathParts[1:]
	if not pathParts:
		raise ValueError(f"Workday URL has no site name: {siteUrl}")
	return f"{parsed.scheme}://{parsed.hostname}", tenant, pathParts[0]


def postWorkdayPage(url: str, payload: dict) -> dict:
	# Workday's CXS API answers 429 to aiohttp/urllib clients but not to requests (header/TLS
	# fingerprinting), so this one source uses requests in a worker thread.
	import requests
	for attempt in range(3):
		response = requests.post(url, json=payload, headers={"Accept": "application/json"}, timeout=requestTimeoutSeconds)
		if response.status_code == 429 and attempt < 2:
			time.sleep(10 * (attempt + 1))
			continue
		response.raise_for_status()
		return response.json()
	raise RuntimeError(f"gave up on {url}")


async def fetchWorkday(source: dict) -> dict[str, Any]:
	origin, tenant, site = parseWorkdaySiteUrl(source["url"])
	apiUrl = f"{origin}/wday/cxs/{tenant}/{site}/jobs"
	jobs = []
	total = 0
	offset = 0
	for _ in range(maxPages):
		payload = await asyncio.to_thread(postWorkdayPage, apiUrl, {
			"appliedFacets": source.get("facets", {}), "limit": 20, "offset": offset, "searchText": source.get("searchText", "")})
		postings = requireList(payload.get("jobPostings") if isinstance(payload, dict) else None, "Workday")
		if offset == 0:
			total = int(payload.get("total") or 0)
		for posting in postings:
			externalPath = posting.get("externalPath") or ""
			bulletFields = posting.get("bulletFields") or []
			stableId = bulletFields[0] if bulletFields else externalPath
			jobs.append(makeJob(posting.get("title"), stableId, f"{origin}/en-US/{site}{externalPath}",
				posting.get("locationsText"), "", "", posting.get("postedOn")))
		offset = offset + len(postings)
		if len(postings) == 0 or offset >= total:
			break
	return result(jobs, total == 0)


zohoJobsInputPattern = re.compile(r'<input[^>]*\bid="jobs"[^>]*>', re.I)
zohoValuePattern = re.compile(r'value="([^"]*)"')


def zohoSlug(title: str) -> str:
	return re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")


async def fetchZohoRecruit(source: dict) -> dict[str, Any]:
	"""Zoho Recruit career sites embed every posting as JSON in <input type=hidden id="jobs">."""
	careersUrl = source["url"].rstrip("/")
	async with newSession({"Accept": "text/html"}) as session:
		async with session.get(careersUrl) as response:
			response.raise_for_status()
			html = await response.text()
	inputMatch = zohoJobsInputPattern.search(html)
	valueMatch = zohoValuePattern.search(inputMatch.group(0)) if inputMatch else None
	if valueMatch is None:
		raise ValueError("Zoho Recruit page has no jobs data (blocked or layout changed)")
	import html as htmlLib
	postings = requireList(json.loads(htmlLib.unescape(valueMatch.group(1))), "Zoho Recruit")
	published = [posting for posting in postings if posting.get("Publish", True)]
	jobs = []
	for posting in published:
		title = clean(posting.get("Posting_Title") or posting.get("Job_Opening_Name"))
		link = f"{careersUrl}/{posting.get('id')}/{zohoSlug(title)}?source=CareerSite"
		stableId = link if source.get("idFrom") == "link" else str(posting.get("id") or "")
		location = joinParts([posting.get("City"), posting.get("State"), posting.get("Country")])
		if posting.get("Remote_Job"):
			location = joinParts([location, "Remote"])
		jobs.append(makeJob(title, stableId, link, location, posting.get("Industry"), posting.get("Job_Type"), posting.get("Date_Opened")))
	return result(jobs, len(published) == 0)


async def fetchPinpoint(source: dict) -> dict[str, Any]:
	async with newSession() as session:
		payload = await requestJson(session, f"https://{source['slug']}.pinpointhq.com/postings.json")
	postings = requireList(payload.get("data") if isinstance(payload, dict) else None, "Pinpoint")
	jobs = [makeJob(
		posting.get("title"), posting.get("id") or "", posting.get("url"),
		(posting.get("location") or {}).get("name"), ((posting.get("job") or {}).get("department") or {}).get("name"),
		joinParts([posting.get("employment_type_text"), posting.get("workplace_type_text")]), posting.get("deadline_at") or "",
	) for posting in postings]
	return result(jobs, len(postings) == 0)


async def fetchManatal(source: dict) -> dict[str, Any]:
	slug = source["slug"]
	url = f"https://core.api.manatal.com/open/v3/career-page/{slug}/jobs/?page_size=100"
	postings: list = []
	async with newSession() as session:
		for _ in range(maxPages):
			payload = await requestJson(session, url)
			postings.extend(requireList(payload.get("results") if isinstance(payload, dict) else None, "Manatal"))
			url = payload.get("next")
			if not url:
				break
	jobs = [makeJob(
		posting.get("position_name"), str(posting.get("id") or ""), f"https://www.careers-page.com/{slug}/job/{posting.get('hash')}",
		posting.get("location_display") or joinParts([posting.get("city"), posting.get("country")]), posting.get("department"),
		posting.get("contract_details"), posting.get("created_at"),
	) for posting in postings]
	return result(jobs, len(postings) == 0)


async def fetchTeamtailor(source: dict) -> dict[str, Any]:
	"""Teamtailor career sites render job links as /jobs/<id>-<slug> server-side."""
	from companies._shared import htmljobs
	baseUrl = source["url"].rstrip("/")
	return await htmljobs.fetchHtmlJobs({
		"type": "html", "url": baseUrl + "/jobs", "linkPattern": r"/jobs/\d+-[a-z0-9-]+/?$",
		"titleSelector": "[class*=title], span", "emptyPattern": source.get("emptyPattern", r"no (?:open )?(?:positions|jobs|openings)"),
	})


def pickPath(value: Any, path: str) -> Any:
	for part in [part for part in path.split(".") if part]:
		value = value.get(part) if isinstance(value, dict) else None
	return value


async def fetchJsonApi(source: dict) -> dict[str, Any]:
	async with newSession() as session:
		payload = await requestJson(session, source["url"])
	items = requireList(pickPath(payload, source.get("itemsPath", "")), "JSON API")
	fields = {"title": "title", "id": "id", "location": "location", "department": "department", "jobType": "type", "postedAt": ""}
	fields.update(source.get("fields", {}))
	jobs = []
	for item in items:
		if not isinstance(item, dict):
			continue
		formatValues = {key: clean(value) for key, value in item.items() if not isinstance(value, (dict, list))}
		try:
			link = source["linkTemplate"].format(**formatValues) if source.get("linkTemplate") else source["url"]
		except KeyError:
			link = source["url"]
		jobs.append(makeJob(
			pickPath(item, fields["title"]), clean(pickPath(item, fields["id"])), link,
			pickPath(item, fields["location"]) if fields["location"] else "", pickPath(item, fields["department"]) if fields["department"] else "",
			pickPath(item, fields["jobType"]) if fields["jobType"] else "", pickPath(item, fields["postedAt"]) if fields["postedAt"] else "",
		))
	return result(jobs, len(items) == 0)


async def fetchWithSharedHelper(source: dict) -> dict[str, Any]:
	sourceType = source["type"]
	if sourceType == "bamboohr":
		from companies._shared import bamboohr
		return await bamboohr.fetchOpenings(source["slug"], generateJobId)
	if sourceType == "jazzhr":
		from companies._shared import jazzhr
		return await jazzhr.fetchBoardJobs(source["slug"], generateJobId)
	if sourceType == "rippling":
		from companies._shared import rippling
		return await rippling.fetchBoardJobs(source["url"])
	if sourceType == "joincom":
		from companies._shared import joincom
		return await joincom.fetchBoardJobs(source["slug"], generateJobId)
	if sourceType == "peopleforce":
		from companies._shared import peopleforce
		return await peopleforce.fetchCareersJobs(source["url"], generateJobId)
	raise ValueError(f"unknown source type {sourceType!r}")


fetchers = {
	"greenhouse": fetchGreenhouse,
	"lever": fetchLever,
	"ashby": fetchAshby,
	"workable": fetchWorkable,
	"recruitee": fetchRecruitee,
	"smartrecruiters": fetchSmartRecruiters,
	"breezy": fetchBreezy,
	"personio": fetchPersonio,
	"workday": fetchWorkday,
	"zohorecruit": fetchZohoRecruit,
	"pinpoint": fetchPinpoint,
	"manatal": fetchManatal,
	"teamtailor": fetchTeamtailor,
	"jsonapi": fetchJsonApi,
}


async def fetchSource(source: dict) -> dict[str, Any]:
	sourceType = source["type"]
	if sourceType == "html":
		from companies._shared import htmljobs
		return await htmljobs.fetchHtmlJobs(source)
	fetcher = fetchers.get(sourceType)
	if fetcher is not None:
		return await fetcher(source)
	return await fetchWithSharedHelper(source)
