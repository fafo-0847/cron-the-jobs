"""Offline tests for companies/_shared/ats.py, htmljobs.py and company.py (network calls stubbed)."""
import asyncio
import json
import logging

import pytest

from companies._shared import ats, company, htmljobs


@pytest.fixture
def stubJson(monkeypatch):
	calls = []

	def install(responses):
		async def fakeRequestJson(session, url, method="GET", payload=None, retries=2):
			calls.append((method, url, payload))
			for prefix, value in responses.items():
				if url.startswith(prefix):
					return value(payload) if callable(value) else value
			raise AssertionError(f"unexpected url {url}")
		monkeypatch.setattr(ats, "requestJson", fakeRequestJson)
		return calls
	return install


def run(source):
	return asyncio.run(ats.fetchSource(source))


def test_greenhouse(stubJson):
	stubJson({"https://boards-api.greenhouse.io/v1/boards/acme/jobs": {"jobs": [
		{"id": 4114048005, "title": "Staff Engineer", "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/4114048005",
			"location": {"name": "Lahore"}, "departments": [{"name": "Engineering"}], "first_published": "2026-11-01"}]}})
	fetched = run({"type": "greenhouse", "slug": "acme"})
	job = fetched["jobs"][0]
	assert job["id"] == ats.generateJobId("Staff Engineer", "4114048005")
	assert (job["location"], job["department"]) == ("Lahore", "Engineering")
	assert fetched["confirmedEmpty"] is False


def test_greenhouse_empty_board_is_confirmed_empty(stubJson):
	stubJson({"https://boards-api.greenhouse.io": {"jobs": []}})
	assert run({"type": "greenhouse", "slug": "acme"}) == {"jobs": [], "confirmedEmpty": True}


def test_greenhouse_error_payload_raises(stubJson):
	stubJson({"https://boards-api.greenhouse.io": {"status": 404, "error": "Job not found"}})
	with pytest.raises(ValueError):
		run({"type": "greenhouse", "slug": "gone"})


def test_lever(stubJson):
	stubJson({"https://api.lever.co/v0/postings/acme": [{"id": "abc", "text": "Designer", "hostedUrl": "https://jobs.lever.co/acme/abc",
		"categories": {"location": "Remote", "team": "Design", "commitment": "Full-time"}, "createdAt": 1767225600000}]})
	job = run({"type": "lever", "slug": "acme"})["jobs"][0]
	assert (job["title"], job["location"], job["department"], job["jobType"], job["postedAt"]) == ("Designer", "Remote", "Design", "Full-time", "2026-01-01")


def test_workable_matches_old_scraper_ids(stubJson, monkeypatch):
	monkeypatch.setattr(ats, "workableMinIntervalSeconds", 0)
	stubJson({"https://apply.workable.com/api/v1/widget/accounts/burq": {"jobs": [
		{"title": "VP of Finance", "shortcode": "4D385B6031", "url": "https://apply.workable.com/j/4D385B6031", "department": "Finance",
			"employment_type": "Full-time", "locations": [{"city": "", "region": "", "country": "United States"}], "telecommuting": True}]}})
	job = run({"type": "workable", "slug": "burq"})["jobs"][0]
	assert job["id"] == "f9f4a1a926badf92688bd48598c3dd14"
	assert job["location"] == "United States, Remote"


def test_smartrecruiters_pages_until_total(stubJson):
	def page(payload):
		return {"totalFound": 1, "content": [{"id": "744", "name": "Analyst", "location": {"city": "Karachi", "country": "pk"},
			"department": {"label": "Data"}, "typeOfEmployment": {"label": "Full-time"}, "releasedDate": "2026-11-02"}]}
	calls = stubJson({"https://api.smartrecruiters.com": page})
	fetched = run({"type": "smartrecruiters", "slug": "Acme"})
	assert len(calls) == 1 and fetched["jobs"][0]["link"] == "https://jobs.smartrecruiters.com/Acme/744"


def test_workday_site_url_parsing_and_paging(monkeypatch):
	assert ats.parseWorkdaySiteUrl("https://acme.wd3.myworkdayjobs.com/en-US/External") == ("https://acme.wd3.myworkdayjobs.com", "acme", "External")

	def page(payload):
		offset = payload["offset"]
		postings = [{"title": f"Job {offset + index}", "externalPath": f"/job/Lahore/Job_{offset + index}", "bulletFields": [f"R{offset + index}"],
			"locationsText": "Lahore"} for index in range(20 if offset == 0 else 5)]
		return {"total": 25, "jobPostings": postings}
	calls = []

	def fakePost(url, payload):
		assert url == "https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/External/jobs"
		calls.append(payload)
		return page(payload)
	monkeypatch.setattr(ats, "postWorkdayPage", fakePost)
	fetched = run({"type": "workday", "url": "https://acme.wd3.myworkdayjobs.com/External"})
	assert len(fetched["jobs"]) == 25 and len(calls) == 2
	assert fetched["jobs"][0]["link"] == "https://acme.wd3.myworkdayjobs.com/en-US/External/job/Lahore/Job_0"


CAREERS_HTML = """
<nav><a href="/careers/">Careers</a><a href="/careers/life-at-acme/">Life</a></nav>
<div class="job-card"><h3 class="job-title">Senior Python Engineer</h3><span class="loc">Lahore</span>
  <a href="/careers/senior-python-engineer/">Apply now</a></div>
<div class="job-card"><a href="/careers/qa-engineer/"><h4>QA Engineer</h4></a><span class="loc">Remote</span></div>
<ul><li><a href="https://acme.com/careers/devops-engineer/">DevOps Engineer</a></li></ul>
<p>We have 3 openings</p>
"""


def test_html_links_with_generic_anchor_text_use_card_heading():
	jobs = htmljobs.parseJobs(CAREERS_HTML, {"linkPattern": r"/careers/(?!life-at)[a-z0-9-]+/?$"}, "https://acme.com/careers/")
	assert [job["title"] for job in jobs] == ["Senior Python Engineer", "QA Engineer", "DevOps Engineer"]
	assert jobs[0]["link"] == "https://acme.com/careers/senior-python-engineer/"
	assert jobs[0]["id"] == ats.generateJobId("Senior Python Engineer", "/careers/senior-python-engineer")


def test_html_cards_with_selectors():
	jobs = htmljobs.parseJobs(CAREERS_HTML, {"cardSelector": ".job-card", "locationSelector": ".loc"}, "https://acme.com/careers/")
	assert [(job["title"], job["location"]) for job in jobs] == [("Senior Python Engineer", "Lahore"), ("QA Engineer", "Remote")]


def test_html_title_only_cards_link_to_page():
	html = '<ul class="openings"><li><span>Accountant</span></li><li><span>HR Officer</span></li></ul>'
	jobs = htmljobs.parseJobs(html, {"cardSelector": "ul.openings li", "titleSelector": "span"}, "https://acme.com/careers")
	assert [job["link"] for job in jobs] == ["https://acme.com/careers", "https://acme.com/careers"]
	assert jobs[0]["id"] != jobs[1]["id"]


def test_html_requires_pattern_or_cards():
	with pytest.raises(ValueError):
		htmljobs.parseJobs("<a href='/x'>x</a>", {}, "https://acme.com")


def test_html_empty_notice(monkeypatch):
	async def fakeFetch(url):
		return "<main><h2>Open positions</h2><p>No open positions at the moment.</p></main>"
	monkeypatch.setattr(htmljobs, "fetchPageHttp", fakeFetch)
	fetched = run({"type": "html", "url": "https://acme.com/careers", "linkPattern": "/careers/.+", "emptyPattern": "No open positions"})
	assert fetched == {"jobs": [], "confirmedEmpty": True}


def test_company_fetch_state_logs_error_when_html_matches_nothing(monkeypatch, caplog):
	async def fakeFetch(url):
		return "<main>redesigned page</main>"
	monkeypatch.setattr(htmljobs, "fetchPageHttp", fakeFetch)
	logger = logging.getLogger("acme")
	with caplog.at_level(logging.ERROR):
		state = asyncio.run(company.fetchState({"type": "html", "url": "https://acme.com/careers", "linkPattern": "/careers/.+"}, logger))
	assert state["jobs"] == [] and state["confirmedEmpty"] is False
	assert "no jobs matched" in caplog.text


def test_company_fetch_state_swallows_and_logs_exceptions(monkeypatch, caplog):
	async def broken(source):
		raise RuntimeError("boom")
	monkeypatch.setattr(ats, "fetchSource", broken)
	with caplog.at_level(logging.ERROR):
		state = asyncio.run(company.fetchState({"type": "greenhouse", "slug": "x"}, logging.getLogger("x")))
	assert state["jobs"] == [] and "boom" in caplog.text


def test_company_snapshot_roundtrip_and_keep_on_zero(tmp_path):
	logger = logging.getLogger("acme")
	path = tmp_path / "acme.json"
	assert company.loadSnapshot(path, "https://acme.com")["jobs"] == []
	snapshot = company.buildSnapshot({"jobs": [{"id": "1"}]}, {"jobs": []}, "https://acme.com", logger)
	company.writeSnapshot(path, snapshot)
	loaded = company.loadSnapshot(path, "https://acme.com")
	assert loaded["jobs"] == [{"id": "1"}]
	assert company.buildSnapshot({"jobs": []}, loaded, "https://acme.com", logger) == loaded


def test_generated_module_exposes_main_py_interface(tmp_path, monkeypatch):
	import importlib.util
	import sys
	from pathlib import Path

	toolsPath = Path(__file__).resolve().parent.parent / "tools"
	sys.path.insert(0, str(toolsPath))
	try:
		import new_company
	finally:
		sys.path.remove(str(toolsPath))
	monkeypatch.setattr(new_company, "repoRoot", tmp_path)
	modulePath = new_company.writeCompany("acme", "https://acme.com/careers", {"type": "html", "url": "https://acme.com/careers", "render": True, "linkPattern": "/jobs/"})
	spec = importlib.util.spec_from_file_location("acme_module", modulePath)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	assert module.source["render"] is True
	for name in ("fetchState", "loadExistingSnapshot", "buildSnapshot", "writeSnapshot", "snapshotPath"):
		assert hasattr(module, name)
	assert module.snapshotPath == modulePath.with_name("acme.json")
	with pytest.raises(SystemExit):
		(tmp_path / "companies" / "manual").mkdir(parents=True)
		(tmp_path / "companies" / "manual" / "manual.py").write_text("# hand written\n")
		new_company.writeCompany("manual", "https://x", {"type": "lever", "slug": "x"})


def test_location_filter_for_global_employers(monkeypatch):
	async def fakeSource(source):
		return {"jobs": [ats.makeJob("Engineer", "1", "x", "Dublin, Ireland"), ats.makeJob("Analyst", "2", "y", "Lahore, Pakistan")], "confirmedEmpty": False}
	monkeypatch.setattr(ats, "fetchSource", fakeSource)
	state = asyncio.run(company.fetchState({"type": "greenhouse", "slug": "x", "locationFilter": "Pakistan"}, logging.getLogger("x")))
	assert [job["title"] for job in state["jobs"]] == ["Analyst"]
	state = asyncio.run(company.fetchState({"type": "greenhouse", "slug": "x", "locationFilter": "Karachi"}, logging.getLogger("x")))
	assert state == {"jobs": [], "state": "open", "confirmedEmpty": True}


def test_json_ld_item_list_and_job_posting():
	html = ('<script type="application/ld+json">{"@graph":[{"@type":"ItemList","itemListElement":[{"@type":"ListItem","position":1,'
		'"name":"AWS Cloud Architect","url":"https://acme.co/careers/aws-cloud-architect"}]}]}</script>'
		'<script type="application/ld+json">{"@type":"JobPosting","title":"QA Engineer","url":"/jobs/qa","employmentType":["FULL_TIME"],'
		'"jobLocation":{"@type":"Place","address":{"addressLocality":"Lahore","addressCountry":"PK"}}}</script>')
	jobs = htmljobs.parseJobs(html, {"jsonLd": True}, "https://acme.co/careers")
	assert [(job["title"], job["link"], job["location"]) for job in jobs] == [
		("AWS Cloud Architect", "https://acme.co/careers/aws-cloud-architect", ""), ("QA Engineer", "https://acme.co/jobs/qa", "Lahore, PK")]


def test_card_stops_before_sibling_job_links():
	html = ('<div class="grid"><div><h3>Senior AI Engineer</h3><a href="/careers/ai">Apply</a></div>'
		'<div><h3>MERN Developer</h3><a href="/careers/mern">Apply</a></div></div>')
	jobs = htmljobs.parseJobs(html, {"linkPattern": "/careers/[a-z]+$"}, "https://acme.co/careers")
	assert [job["title"] for job in jobs] == ["Senior AI Engineer", "MERN Developer"]


def test_json_api_source(stubJson):
	stubJson({"https://acme.co/api/jobs": {"data": [{"id": 8, "title": "Back-end Developer", "location": "Lahore", "type": "Full-Time", "slug": "back-end-developer-OK"}]}})
	fetched = run({"type": "jsonapi", "url": "https://acme.co/api/jobs", "itemsPath": "data", "linkTemplate": "https://acme.co/career/{slug}"})
	job = fetched["jobs"][0]
	assert (job["title"], job["location"], job["jobType"], job["link"]) == ("Back-end Developer", "Lahore", "Full-Time", "https://acme.co/career/back-end-developer-OK")
	assert job["id"] == ats.generateJobId("Back-end Developer", "8")
