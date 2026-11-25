"""Find a company's careers page and job source (ATS), and count current jobs.

Usage:
  python tools/discover_careers.py input.json output.json [--concurrency 8]

input.json: [{"name": "emumba", "website": "https://www.emumba.com/open-positions/"}, ...]
Each result lists careersUrl, detected source config (if any), job count and sample titles,
plus candidate links, so a human can review it and then run tools/new_company.py.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from companies._shared import ats, htmljobs  # noqa: E402

careerWordPattern = re.compile(r"career|jobs?\b|join[\s_-]?(?:us|our|the)|hiring|vacanc|openings?|open[\s_-]?positions?|work[\s_-]?with[\s_-]?us|life[\s_-]?at|opportunit", re.I)
commonPaths = ["/careers", "/careers/", "/career", "/jobs", "/join-us", "/careers.html", "/about/careers", "/company/careers"]
atsSignatures = [
	("greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([A-Za-z0-9_-]+)", re.I)),
	("greenhouse", re.compile(r"greenhouse\.io/embed/job_board/js\?for=([A-Za-z0-9_-]+)", re.I)),
	("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_.-]+)", re.I)),
	("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)", re.I)),
	("workable", re.compile(r"apply\.workable\.com/(?!api\b|j\b)([A-Za-z0-9_-]+)", re.I)),
	("recruitee", re.compile(r"//([a-z0-9-]+)\.recruitee\.com", re.I)),
	("smartrecruiters", re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([A-Za-z0-9_-]+)", re.I)),
	("breezy", re.compile(r"//([a-z0-9-]+)\.breezy\.hr", re.I)),
	("bamboohr", re.compile(r"//([a-z0-9-]+)\.bamboohr\.com", re.I)),
	("jazzhr", re.compile(r"//([a-z0-9-]+)\.applytojob\.com", re.I)),
	("jazzhr", re.compile(r"app\.jazz\.co/widgets/basic/create/([a-z0-9-]+)", re.I)),
	("rippling", re.compile(r"ats\.rippling\.com/(?:[a-z]{2}-[A-Z]{2}/)?([a-z0-9-]+)/jobs", re.I)),
	("joincom", re.compile(r"join\.com/companies/([a-z0-9-]+)", re.I)),
	("peopleforce", re.compile(r"//([a-z0-9-]+)\.peopleforce\.io", re.I)),
	("personio", re.compile(r"//([a-z0-9-]+)\.jobs\.personio\.(?:de|com)", re.I)),
	("pinpoint", re.compile(r"//([a-z0-9-]+)\.pinpointhq\.com", re.I)),
	("manatal", re.compile(r"careers-page\.com/([a-z0-9-]+)", re.I)),
	("teamtailor", re.compile(r"(https://[a-z0-9-]+\.teamtailor\.com)", re.I)),
	("zohorecruit", re.compile(r"(https://[a-z0-9-]+\.zohorecruit\.(?:com|eu|in)/(?:jobs/[A-Za-z0-9_-]+|careers))", re.I)),
	("workday", re.compile(r"(https://[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?[A-Za-z0-9_-]+)", re.I)),
]
otherPlatforms = re.compile(r"teamtailor\.com|zohorecruit|recruit\.zoho|careers-page\.com|manatal|freshteam\.com|rozee\.pk|odoo\.com/jobs|/jobs/detail/|keka\.com|darwinbox|successfactors|taleo|icims|oraclecloud\.com|dayforcehcm|ultipro|paylocity|bayzat|hirehive|pinpointhq|comeet|gohire|hrmos|myhcm\.pk|webhr\.co|kenjo|factorial|jobvite|polymer\.co|wellfound|linkedin\.com/company/[^\"']+/jobs", re.I)
defaultJobLinkPattern = r"/(?:jobs?|careers?|positions?|openings?|vacanc(?:y|ies)|opportunit(?:y|ies)|apply)/[^/?#]*[a-z0-9][^/?#]*/?(?:[?#].*)?$"


def normalizeWebsite(website: str) -> str:
	website = website.strip()
	if not website:
		return ""
	if not re.match(r"https?://", website, re.I):
		website = "https://" + website
	parsed = urlparse(website)
	return f"https://{parsed.netloc.lower()}{parsed.path}" + (f"?{parsed.query}" if parsed.query else "")


async def fetchText(session: aiohttp.ClientSession, url: str) -> tuple[int, str, str]:
	try:
		async with session.get(url, allow_redirects=True) as response:
			text = await response.text(errors="replace")
			return response.status, str(response.url), text
	except Exception as error:
		return 0, url, f"__error__ {type(error).__name__}: {error}"


def detectSources(html: str) -> list[dict]:
	found: list[dict] = []
	for sourceType, pattern in atsSignatures:
		for match in pattern.finditer(html):
			value = match.group(1)
			if sourceType == "teamtailor":
				source = {"type": "teamtailor", "url": value.lower()}
			elif sourceType == "zohorecruit":
				source = {"type": "zohorecruit", "url": value if "/jobs/" in value else value.rsplit("/", 1)[0] + "/jobs/Careers"}
			elif sourceType == "workday":
				source = {"type": "workday", "url": value}
			elif sourceType == "rippling":
				source = {"type": "rippling", "url": f"https://ats.rippling.com/{value}/jobs"}
			elif sourceType == "breezy":
				source = {"type": "breezy", "url": f"https://{value.lower()}.breezy.hr"}
			elif sourceType == "peopleforce":
				source = {"type": "peopleforce", "url": f"https://{value.lower()}.peopleforce.io/careers"}
			else:
				source = {"type": sourceType, "slug": value}
			if source not in found and value.lower() not in ("www", "api", "embed", "assets", "static", "cdn", "app"):
				found.append(source)
	return found


def careerLinks(html: str, baseUrl: str) -> list[str]:
	links: list[tuple[int, str]] = []
	baseHost = urlparse(baseUrl).netloc.replace("www.", "")
	for match in re.finditer(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', html, re.S | re.I):
		href = urljoin(baseUrl, match.group(1).strip())
		text = re.sub(r"<[^>]+>", " ", match.group(2))
		if not href.startswith("http"):
			continue
		score = 0
		if careerWordPattern.search(urlparse(href).path):
			score += 2
		if careerWordPattern.search(text):
			score += 1
		host = urlparse(href).netloc.replace("www.", "")
		if score and (host == baseHost or host.endswith("." + baseHost) or otherPlatforms.search(href) or detectSources(href)):
			links.append((score, href))
	ordered = [href for _, href in sorted(links, key=lambda item: -item[0])]
	return list(dict.fromkeys(ordered))[:4]


async def countSource(source: dict) -> tuple[int, list[str], str]:
	if source["type"] == "workable" and "--count-workable" not in sys.argv:
		return -2, [], "not counted (Workable rate-limits bulk requests)"
	try:
		fetched = await asyncio.wait_for(ats.fetchSource(source), 90)
		return len(fetched["jobs"]), [job["title"] for job in fetched["jobs"][:6]], "empty" if fetched["confirmedEmpty"] else ""
	except Exception as error:
		return -1, [], f"{type(error).__name__}: {str(error)[:150]}"


async def discover(entry: dict, session: aiohttp.ClientSession) -> dict:
	website = normalizeWebsite(entry.get("website", ""))
	record: dict = {"name": entry["name"], "website": website, "careersUrl": "", "sources": [], "platformHints": [], "notes": []}
	if not website:
		record["notes"].append("no website")
		return record
	status, finalUrl, homeHtml = await fetchText(session, website)
	if status == 0 or status >= 400:
		alternate = website.replace("https://", "http://") if status == 0 else website
		status, finalUrl, homeHtml = await fetchText(session, alternate)
	record["homeStatus"] = status
	if status == 0 or status >= 400:
		record["notes"].append(f"website unreachable: {homeHtml[:120] if status == 0 else status}")
		return record
	pages = [(finalUrl, homeHtml)]
	candidates = careerLinks(homeHtml, finalUrl)
	looksLikeCareersPage = careerWordPattern.search(urlparse(website).path or "") is not None
	if looksLikeCareersPage:
		candidates.insert(0, finalUrl)
	if not candidates:
		origin = f"{urlparse(finalUrl).scheme}://{urlparse(finalUrl).netloc}"
		candidates = [origin + path for path in commonPaths]
	record["candidates"] = candidates
	for candidate in candidates:
		if candidate == finalUrl:
			continue
		candidateStatus, candidateFinal, candidateHtml = await fetchText(session, candidate)
		if 200 <= candidateStatus < 400:
			pages.append((candidateFinal, candidateHtml))
			if not record["careersUrl"] and not otherPlatforms.search(candidateFinal):
				record["careersUrl"] = candidateFinal
		for nested in careerLinks(candidateHtml, candidateFinal)[:2]:
			if detectSources(nested) or otherPlatforms.search(nested):
				nestedStatus, nestedFinal, nestedHtml = await fetchText(session, nested)
				if 200 <= nestedStatus < 400:
					pages.append((nestedFinal, nestedHtml))
	if looksLikeCareersPage:
		record["careersUrl"] = finalUrl
	for pageUrl, html in pages:
		for source in detectSources(pageUrl + " " + html):
			if source not in record["sources"]:
				record["sources"].append(source)
		for hint in otherPlatforms.findall(pageUrl + " " + html):
			if hint not in record["platformHints"]:
				record["platformHints"].append(hint)
	for source in record["sources"][:4]:
		count, titles, note = await countSource(source)
		source["jobCount"] = count
		source["sample"] = titles
		if note:
			source["note"] = note
	if record["careersUrl"]:
		careersHtml = next((html for url, html in pages if url == record["careersUrl"]), "")
		try:
			linkJobs = htmljobs.parseJobs(careersHtml, {"linkPattern": defaultJobLinkPattern}, record["careersUrl"])
		except Exception:
			linkJobs = []
		record["htmlLinkJobs"] = [(job["title"], job["link"]) for job in linkJobs[:12]]
		record["htmlLinkJobCount"] = len(linkJobs)
		record["careersTextLength"] = len(re.sub(r"<[^>]+>", " ", careersHtml))
	return record


async def main() -> None:
	inputPath, outputPath = sys.argv[1], sys.argv[2]
	concurrency = int(sys.argv[sys.argv.index("--concurrency") + 1]) if "--concurrency" in sys.argv else 8
	entries = json.loads(Path(inputPath).read_text())
	semaphore = asyncio.Semaphore(concurrency)
	headers = {"User-Agent": ats.userAgent, "Accept": "text/html,application/xhtml+xml"}
	results: list[dict] = []
	async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=25)) as session:
		async def run(entry: dict) -> None:
			async with semaphore:
				try:
					record = await asyncio.wait_for(discover(entry, session), 240)
				except Exception as error:
					record = {"name": entry["name"], "website": entry.get("website", ""), "notes": [f"discovery failed: {error}"]}
				results.append(record)
				best = max((source.get("jobCount", -1) for source in record.get("sources", [])), default=None)
				print(f"{record['name']:30} sources={[source['type'] for source in record.get('sources', [])]} best={best} html={record.get('htmlLinkJobCount')} {record.get('careersUrl', '')} {record.get('notes', '')}", flush=True)
		await asyncio.gather(*(run(entry) for entry in entries))
	order = {entry["name"]: index for index, entry in enumerate(entries)}
	results.sort(key=lambda record: order.get(record["name"], 0))
	Path(outputPath).write_text(json.dumps(results, indent=1, ensure_ascii=False))


if __name__ == "__main__":
	asyncio.run(main())
