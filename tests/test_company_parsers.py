"""Offline parser tests for the scrapers fixed in Nov 2026. Markup mirrors what each live page served."""
import asyncio
import json

import pytest

from companies.carbonteq import carbonteq
from companies.chainfore import chainfore
from companies.datasciencedojo import datasciencedojo
from companies.devntech import devntech
from companies.dubizzle import dubizzle
from companies.folio3 import folio3
from companies.funavry import funavry
from companies.harmonicai import harmonicai
from companies.ocloud import ocloud
from companies.persivia import persivia
from companies.phaedra import phaedra
from companies.purelogics import purelogics
from companies.xeven import xeven


def flightPush(payload: str) -> str:
	return "<script>self.__next_f.push([1," + json.dumps(payload) + "])</script>"


def test_folio3_reads_jobs_from_flight_data():
	jobs = [{"id": "13", "slug": "microsoft-power-automate-rpa-developer", "title": "Microsoft Power Automate / RPA Developer", "division": "Dynamics", "location": "Riyadh, Saudi Arabia", "jobType": "Regular", "summary": "x"}]
	html = flightPush('5:["$","$L1",null,{"jobs":' + json.dumps(jobs) + "}]\n")
	parsed = folio3.parseJobsFromHtml(html, "https://www.folio3.com/careers")
	assert parsed[0]["link"] == "https://www.folio3.com/careers/microsoft-power-automate-rpa-developer"
	assert (parsed[0]["department"], parsed[0]["location"], parsed[0]["jobType"]) == ("Dynamics", "Riyadh, Saudi Arabia", "Regular")


def test_carbonteq_track_page_roles_and_empty_notice():
	card = ('["$","div",null,{"className":"careers-d_flex","children":[["$","p",null,{"ref":"$undefined","className":"careers-text careers-td_underline",'
		'"children":"Associate Software Engineer"}],["$","p",null,{"ref":"$undefined","className":"careers-text--color_muted","children":"Lahore, Punjab, Pakistan"}]]}],'
		'["$","$L2f",null,{"href":"/careers/jobs/37de6050-4107-4d95-b29b-92735df0b951/apply","className":"x","children":"Apply"}]]}],'
		'["$","div",null,{"children":[["$","$L2a",null,{"children":"Full-Time"}],["$","$L2a",null,{"children":"On-Site"}]]}]')
	result = carbonteq.parseTrackPage(flightPush(card), "engineering")
	job = result["jobs"][0]
	assert job["title"] == "Associate Software Engineer"
	assert job["link"] == "https://www.carbonteq.com/careers/jobs/37de6050-4107-4d95-b29b-92735df0b951/apply"
	assert job["location"] == "Lahore, Punjab, Pakistan"
	assert job["jobType"] == "Full-Time, On-Site"
	assert carbonteq.parseTrackPage("<p>No open roles right now</p><p>Stay tuned</p>", "talent") == {"jobs": [], "empty": True}
	with pytest.raises(ValueError):
		carbonteq.parseTrackPage("<html>redesigned</html>", "design")


def test_chainfore_open_roles_section():
	emptyHtml = '<section><h2>Open roles</h2></div><div class="rv"><p class="wide lead">No roles are open right now. You can still send a note</p></div></section><section>'
	assert chainfore.parseOpenRoles(emptyHtml) == {"jobs": [], "confirmedEmpty": True}
	rolesHtml = '<h2>Open roles</h2><div><h3>Senior AI Engineer</h3><p>Lahore</p><h3>Cloud Architect</h3></div><section>'
	assert [job["title"] for job in chainfore.parseOpenRoles(rolesHtml)["jobs"]] == ["Senior AI Engineer", "Cloud Architect"]
	with pytest.raises(ValueError):
		chainfore.parseOpenRoles("<main>no such section</main>")


def test_persivia_job_list():
	html = ('<ul class="job-list"><li class="job-list__item"><span class="job-list__bullet"></span><span class="job-list__title">Senior Program Director</span></li>'
		'<li class="job-list__item"><span class="job-list__bullet"></span><span class="job-list__title">SME Quality</span></li></ul>')
	assert [job["title"] for job in persivia.parseJobList(html)] == ["Senior Program Director", "SME Quality"]
	with pytest.raises(ValueError):
		persivia.parseJobList("<div>no list</div>")


def test_datasciencedojo_role_cards_and_jsonld_fallback():
	cards = ('<ul class="roles"><li><a href="/jobs/marketing-specialist/" class="role" data-astro-cid-x=""><span class="role-category" data-astro-cid-x="">Marketing</span>'
		'<span class="role-title" data-astro-cid-x="">Marketing Specialist</span><span class="role-meta" data-astro-cid-x="">Remote · Full Time</span></a></li></ul>')
	job = datasciencedojo.parseJobsFromHtml(cards)[0]
	assert job["link"] == "https://datasciencedojo.com/jobs/marketing-specialist/"
	assert (job["department"], job["location"], job["jobType"]) == ("Marketing", "Remote", "Full Time")
	jsonLd = {"@graph": [{"@type": "ItemList", "@id": "https://datasciencedojo.com/about/careers/#open-roles", "itemListElement": [{"name": "Marketing Specialist", "url": "https://datasciencedojo.com/jobs/marketing-specialist/"}]}]}
	fallbackHtml = '<script type="application/ld+json">' + json.dumps(jsonLd) + "</script>"
	assert datasciencedojo.parseJobsFromHtml(fallbackHtml)[0]["id"] == job["id"]


def test_devntech_roles_section():
	html = ('<section id="roles" class="section"><div class="mt-10 grid"><div class="flex h-full flex-col rounded-[6px] border bg-white p-6">'
		'<p class="text-[20px] font-bold">Associate Software Engineer</p><div class="mt-2 flex"><span class="rounded-md bg-surface px-2.5">On Site</span>'
		'<span class="rounded-md bg-surface px-2.5">0-1 years</span></div><p class="mt-4">Entry-level role.</p>'
		'<a target="_blank" class="mt-6" href="https://devntech.odoo.com/jobs/associate-software-engineer-4">Apply now</a></div></div></section>')
	job = devntech.parseRolesHtml(html)[0]
	assert job["id"] == "955ec929e82388a3419a44044150ea57"
	assert (job["location"], job["experience"], job["description"]) == ("On Site", "0-1 years", "Entry-level role.")


def test_ocloud_posts_keep_old_ids():
	posts = [
		{"id": "cG9zdDoyMzIx", "title": "Ruby On Rails Developer", "date": "2026-07-01", "categories": {"nodes": [{"name": "Developers"}, {"name": "job"}]},
			"excerpt": "<p>Intro<br />\njobType=Full Time<br />\nexperience=2 years<br />\nlocation=Lahore<br />\n</p>"},
		{"id": "cG9zdDo5OTk=", "title": "A blog post", "categories": {"nodes": [{"name": "blog"}]}, "excerpt": ""},
	]
	jobs = ocloud.parsePosts(posts)
	assert len(jobs) == 1
	assert jobs[0]["id"] == "8025e9d3ea6db756870013e0cd2062c0"
	assert (jobs[0]["location"], jobs[0]["jobType"], jobs[0]["department"]) == ("Lahore", "Full Time", "Developers")


def test_dubizzle_breezy_positions():
	positions = [{"name": "Admin Officer", "url": "https://dubizzlelabs.breezy.hr/p/fc3f-admin-officer", "department": "Admin",
		"type": {"name": "Full-Time"}, "location": {"name": "Lahore, PK"}, "published_date": "2026-11-20"}]
	job = dubizzle.parsePositions(positions)[0]
	assert (job["title"], job["location"], job["department"], job["jobType"]) == ("Admin Officer", "Lahore, PK", "Admin", "Full-Time")


def test_xeven_role_rows():
	html = ('<div class="roles"><div class="role-row"><h4>Senior AI/ML Engineer</h4><span class="meta">Engineering</span><span class="meta">Lahore / Remote</span>'
		'<span class="ar">→</span></div><div class="role-row"><h4>Product Designer</h4><span class="meta">Design</span><span class="meta">Lahore</span></div></div>')
	jobs = xeven.parseRolesHtml(html)
	assert [(job["title"], job["department"], job["location"]) for job in jobs] == [("Senior AI/ML Engineer", "Engineering", "Lahore / Remote"), ("Product Designer", "Design", "Lahore")]


def test_phaedra_elementor_loop_items_keep_old_ids():
	html = ('<div data-elementor-type="loop-item" data-elementor-id="51940" class="elementor e-loop-item post-51945 job type-job status-publish hentry department-business">'
		'<div class="elementor-element elementor-element-jc0loc1 elementor-widget"><p class="elementor-heading-title">On-Site - Lahore</p></div>'
		'<div class="elementor-element elementor-element-jc0exp1 elementor-widget"><p class="elementor-heading-title">4+ years</p></div>'
		'<div class="elementor-element elementor-element-jc0ttl1 elementor-widget"><h3 class="elementor-heading-title">Sales Executive</h3></div>'
		'<div class="elementor-element elementor-element-jc0btn1"><a class="elementor-button" href="https://forms.clickup.com/3316051/f/356ak-128858/NQP8QW0XKVWS20MPQU">Apply</a></div></div>'
		'<div data-elementor-type="loop-item" class="elementor e-loop-item post-1 page type-page"><h3>Not a job</h3></div>')
	jobs = phaedra.parseJobsHtml(html)
	assert len(jobs) == 1
	assert jobs[0]["id"] == "81d2d1c1208ee2e3d86d97b717ad194d"
	assert (jobs[0]["department"], jobs[0]["location"], jobs[0]["experience"]) == ("Business", "On-Site - Lahore", "4+ years")


def test_funavry_role_cards():
	html = ('<li><a href="/careers/inbound-sales-representative" class="group"><div><h3 class="text-ink">Inbound Sales Representative</h3>'
		'<span class="rounded-sm">On-site</span></div><span class="mt-0.5">Posted <!-- -->24 Oct</span><p>'
		'<span class="inline-flex"><svg class="lucide lucide-map-pin text-ink-400"><path d=""></path></svg>Islamabad , Pakistan</span>'
		'<span class="inline-flex"><svg class="lucide lucide-briefcase text-ink-400"><rect></rect></svg>Full-time</span></p></a></li>')
	job = funavry.parseRolesHtml(html)[0]
	assert job["link"] == "https://www.funavry.com/careers/inbound-sales-representative"
	assert (job["location"], job["jobType"], job["workMode"], job["postedAt"]) == ("Islamabad, Pakistan", "Full-time", "On-site", "24 Oct")


def test_purelogics_api_items():
	items = [{"id": 2282, "title": "Associate BD (LinkedIn + Email)", "location": "Lahore", "job_type": "FULL_TIME", "working_model": "ONSITE",
		"department_name": "Business Development / LinkedIn", "posted_at": "2026-11-11T12:02:02"}]
	job = purelogics.parseApiJobs(items)[0]
	assert job["link"] == "https://hiring.purelogics.com/careers/job/2282"
	assert job["jobType"] == "Full Time, Onsite"


def test_harmonic_ashby_job():
	job = harmonicai.parseAshbyJob({"id": "e3b5", "title": "Account Manager", "location": "New York City", "department": "Sales",
		"employmentType": "FullTime", "jobUrl": "https://jobs.ashbyhq.com/harmonic-ai/e3b5", "publishedAt": "2026-11-01"})
	assert job["link"] == "https://jobs.ashbyhq.com/harmonic-ai/e3b5" and job["department"] == "Sales"
	assert harmonicai.parseAshbyJob({"title": ""}) is None
