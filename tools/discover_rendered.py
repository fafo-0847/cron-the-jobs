"""Second discovery pass in a real browser (for JS-rendered sites and widgets).

Usage:
  python tools/discover_rendered.py discover_out.json rendered_out.json pagesDir [--concurrency 4] [--only name1,name2]

For each company without a detected ATS it loads the homepage and the best careers
link in Chromium, records network requests and iframes (ATS widgets often load via
JS), detects job sources, counts links that look like job postings and saves the
rendered careers HTML to pagesDir/<name>.html for review.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright  # noqa: E402

from companies._shared import browser as sharedBrowser  # noqa: E402
from companies._shared import htmljobs  # noqa: E402
from tools.discover_careers import careerLinks, careerWordPattern, countSource, defaultJobLinkPattern, detectSources, normalizeWebsite, otherPlatforms  # noqa: E402

blockedResourceTypes = {"image", "media", "font"}


async def renderPage(context, url: str) -> tuple[str, str, list[str]]:
	page = await context.new_page()
	requested: list[str] = []
	page.on("request", lambda request: requested.append(request.url))
	await page.route("**/*", lambda route: route.abort() if route.request.resource_type in blockedResourceTypes else route.continue_())
	try:
		response = await page.goto(url, wait_until="domcontentloaded", timeout=40000)
		try:
			await page.wait_for_load_state("networkidle", timeout=12000)
		except Exception:
			pass
		await page.mouse.wheel(0, 4000)
		await page.wait_for_timeout(2500)
		html = await page.content()
		frameUrls = [frame.url for frame in page.frames[1:]]
		status = response.status if response else 0
		if status >= 400:
			html = f"__status__ {status}\n" + html
		return page.url, html, requested + frameUrls
	finally:
		await page.close()


def visibleText(html: str) -> str:
	text = re.sub(r"<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>", " ", html, flags=re.S | re.I)
	text = re.sub(r"<[^>]+>", " ", text)
	return re.sub(r"\s+", " ", text).strip()


async def renderCompany(browserInstance, record: dict, pagesDir: Path) -> dict:
	context = await browserInstance.new_context(user_agent=sharedBrowser.desktopUserAgent, locale="en-US")
	result: dict = {"name": record["name"], "website": record.get("website", ""), "sources": [], "platformHints": [], "notes": []}
	try:
		website = normalizeWebsite(record.get("website", ""))
		if not website:
			result["notes"].append("no website")
			return result
		try:
			homeUrl, homeHtml, homeRequests = await renderPage(context, website)
		except Exception as error:
			result["notes"].append(f"home failed: {str(error).splitlines()[0][:120]}")
			return result
		result["homeUrl"] = homeUrl
		careersCandidates = []
		if record.get("careersUrl"):
			careersCandidates.append(record["careersUrl"])
		if careerWordPattern.search(urlparse(website).path or ""):
			careersCandidates.insert(0, homeUrl)
		careersCandidates += careerLinks(homeHtml, homeUrl)
		careersCandidates = list(dict.fromkeys(careersCandidates))[:3]
		allSignals = homeUrl + " " + homeHtml + " " + " ".join(homeRequests)
		careersUrl, careersHtml = "", ""
		for candidate in careersCandidates:
			try:
				finalUrl, html, requests = await renderPage(context, candidate) if candidate != homeUrl else (homeUrl, homeHtml, homeRequests)
			except Exception as error:
				result["notes"].append(f"careers failed {candidate}: {str(error).splitlines()[0][:100]}")
				continue
			allSignals += " " + finalUrl + " " + html + " " + " ".join(requests)
			if not careersUrl and not html.startswith("__status__"):
				careersUrl, careersHtml = finalUrl, html
		result["careersUrl"] = careersUrl
		result["candidates"] = careersCandidates
		for source in detectSources(allSignals):
			if source not in result["sources"]:
				result["sources"].append(source)
		result["platformHints"] = sorted(set(hint.lower() for hint in otherPlatforms.findall(allSignals)))
		if careersHtml:
			(pagesDir / f"{record['name']}.html").write_text(careersHtml, encoding="utf-8")
			try:
				linkJobs = htmljobs.parseJobs(careersHtml, {"linkPattern": defaultJobLinkPattern}, careersUrl)
			except Exception:
				linkJobs = []
			result["htmlLinkJobs"] = [(job["title"], job["link"]) for job in linkJobs[:15]]
			result["htmlLinkJobCount"] = len(linkJobs)
			text = visibleText(careersHtml)
			anchor = re.search(r"open (?:positions|roles|jobs)|current (?:openings|vacancies)|job openings|we.re hiring|join (?:us|our team)|vacanc", text, re.I)
			result["textSnippet"] = text[anchor.start():anchor.start() + 700] if anchor else text[:500]
		for source in result["sources"][:3]:
			count, titles, note = await countSource(source)
			source["jobCount"], source["sample"] = count, titles
			if note:
				source["note"] = note
	finally:
		await context.close()
	return result


async def main() -> None:
	inputPath, outputPath, pagesDir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
	pagesDir.mkdir(parents=True, exist_ok=True)
	concurrency = int(sys.argv[sys.argv.index("--concurrency") + 1]) if "--concurrency" in sys.argv else 4
	only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else None
	records = json.loads(inputPath.read_text())
	todo = [record for record in records if (only and record["name"] in only) or (not only and not record.get("sources"))]
	results: list[dict] = []
	semaphore = asyncio.Semaphore(concurrency)
	async with async_playwright() as playwright:
		browserInstance = await playwright.chromium.launch()

		async def run(record: dict) -> None:
			async with semaphore:
				try:
					rendered = await asyncio.wait_for(renderCompany(browserInstance, record, pagesDir), 180)
				except Exception as error:
					rendered = {"name": record["name"], "website": record.get("website", ""), "notes": [f"render failed: {type(error).__name__} {error}"]}
				results.append(rendered)
				print(f"{rendered['name']:28} src={[(s['type'], s.get('jobCount')) for s in rendered.get('sources', [])]} links={rendered.get('htmlLinkJobCount')} hints={rendered.get('platformHints')} {rendered.get('careersUrl', '')} {rendered.get('notes')}", flush=True)
				outputPath.write_text(json.dumps(results, indent=1, ensure_ascii=False))

		await asyncio.gather(*(run(record) for record in todo))
		await browserInstance.close()
	outputPath.write_text(json.dumps(results, indent=1, ensure_ascii=False))


if __name__ == "__main__":
	asyncio.run(main())
