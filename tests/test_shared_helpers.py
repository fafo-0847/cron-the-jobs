"""Offline tests for companies/_shared helpers, using markup shapes captured from the live sites (Nov 2026)."""
import json

import pytest

from companies._shared import bamboohr, jazzhr, joincom, nextjs, peopleforce, rippling


def fakeJobId(title: str, stableId: str) -> str:
	return f"{title}|{stableId}"


def flightPush(payload: str) -> str:
	return "<script>self.__next_f.push([1," + json.dumps(payload) + "])</script>"


def test_nextjs_flight_extracts_embedded_job_objects():
	jobsJson = json.dumps([{"id": "12", "slug": "functional-consultant", "title": "Functional Consultant", "division": "NetSuite", "location": "USA", "jobType": "Regular"}])
	html = "<html>" + flightPush('1:["$","ul",null,{"jobs":') + flightPush(jobsJson + "}]\n") + "</html>"
	text = nextjs.extractFlightText(html)
	objects = nextjs.findJsonObjects(text, ["slug", "title", "jobType"])
	assert objects == [json.loads(jobsJson)[0]]


def test_nextjs_find_objects_dedupes_and_requires_keys():
	text = '{"slug":"a","title":"A","jobType":"x"} junk {"slug":"a","title":"A","jobType":"x"} {"slug":"b","title":"B"}'
	assert [o["slug"] for o in nextjs.findJsonObjects(text, ["slug", "title", "jobType"])] == ["a"]


def ripplingPage(items, page=0, totalPages=1, totalItems=None):
	data = {"props": {"pageProps": {"dehydratedState": {"queries": [
		{"queryKey": ["board", "netwrix-corporation", "job-posts", False, {"page": page}], "state": {"data": {
			"items": items, "page": page, "pageSize": 20, "totalItems": len(items) if totalItems is None else totalItems, "totalPages": totalPages}}},
		{"queryKey": ["board", "netwrix-corporation", "locations"], "state": {"data": {"items": [{"name": "Canada"}]}}},
	]}}}}
	return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(data) + "</script>"


def test_rippling_parses_job_posts_query_not_other_queries():
	item = {"id": "613a430d", "name": "Director, Customer Success", "url": "https://ats.rippling.com/netwrix-corporation/jobs/613a430d",
		"department": {"name": "Customer Success", "displayName": "Customer Success"},
		"locations": [{"name": "Kraków, Poland", "workplaceType": "ON_SITE"}, {"name": "Remote (US)", "workplaceType": "REMOTE"}]}
	data = rippling.extractJobPostsData(ripplingPage([item], totalPages=2, totalItems=30))
	assert data["totalPages"] == 2
	job = rippling.parseJobItem(data["items"][0])
	assert job["title"] == "Director, Customer Success"
	assert job["location"] == "Kraków, Poland / Remote (US)"
	assert job["department"] == "Customer Success"
	assert job["jobType"] == "ON_SITE, REMOTE"
	assert job["id"] == rippling.generateJobId("Director, Customer Success", "613a430d")


def test_rippling_without_next_data_raises():
	with pytest.raises(ValueError):
		rippling.extractJobPostsData("<html>Just a moment...</html>")


def test_rippling_page_url_replaces_query():
	assert rippling.buildPageUrl("https://ats.rippling.com/en-GB/x/jobs?page=0&jobBoardSlug=x", 2) == "https://ats.rippling.com/en-GB/x/jobs?page=2"


def test_joincom_items_and_empty_board():
	pageData = {"jobs": {"items": [{"idParam": "14757601-venture-development-intern", "title": "Venture Development Intern",
		"city": {"cityName": "Berlin", "countryName": "Germany"}, "employmentType": {"name": "Intern"}, "workplaceType": "HYBRID",
		"category": {"name": "Business"}, "createdAt": "2026-08-01"}], "pagination": {"page": 1, "pageCount": 1, "total": 1}}}
	html = '<script id="__NEXT_DATA__">' + json.dumps({"props": {"pageProps": {"pageData": pageData}}}) + "</script>"
	data = joincom.extractJobsData(html)
	job = joincom.parseItem(data["items"][0], "hivebuy", fakeJobId)
	assert job["id"] == "Venture Development Intern|14757601"
	assert job["link"] == "https://join.com/companies/hivebuy/14757601-venture-development-intern"
	assert job["location"] == "Berlin, Germany"
	assert job["jobType"] == "Intern, HYBRID"


PEOPLEFORCE_PAGE = """
<div class="tw-text-neutral-dark-80 tw-text-xs">
  Displaying <strong>1 - 10</strong> of <strong>38</strong> in total
</div>
<h4 class="tw-text-medium tw-mb-2">
  <a class="tw-stretched-link tw-text-black" data-turbo-frame="_top" href="/careers/v/251727-creative-director">Creative Director</a>
</h4>
<div class="tw-flex tw-items-center"><i class="fas fa-briefcase fa-fw tw-me-1" aria-hidden="true"></i>Marketing
<span>&middot;</span></div>
<div class="tw-flex tw-items-center"><i class="fas fa-sitemap fa-fw tw-me-1" aria-hidden="true"></i>Pakistan/Asia</div>
<div class="tw-flex tw-items-center"><i class="fas fa-clock fa-fw tw-me-1" aria-hidden="true"></i>Full-time</div>
<div class="tw-flex tw-items-center"><i class="fas fa-map-marker-alt fa-fw tw-me-1" aria-hidden="true"></i>NASTP, Lahore</div>
<h4><a class="tw-stretched-link" href="/careers/v/244556-account-executive">Account Executive</a></h4>
<div><i class="fas fa-briefcase fa-fw" aria-hidden="true"></i>Finance</div>
<nav><a href="?page=2">2</a><a href="?page=4">4</a></nav>
"""


def test_peopleforce_parses_cards_and_counter_with_tags():
	parsed = peopleforce.parsePage(PEOPLEFORCE_PAGE, "https://laam.peopleforce.io/careers", fakeJobId)
	assert parsed["total"] == 38 and parsed["perPage"] == 10 and parsed["maxLinkedPage"] == 4
	first, second = parsed["jobs"]
	assert first["title"] == "Creative Director"
	assert first["link"] == "https://laam.peopleforce.io/careers/v/251727-creative-director"
	assert (first["department"], first["jobType"], first["location"]) == ("Marketing", "Full-time", "NASTP, Lahore")
	assert second["department"] == "Finance" and second["location"] == ""


JAZZHR_PAGE = """
<ul class='list-group'>
  <li class="list-group-item">
    <h3 class='list-group-item-heading'>
      <a href="https://cloudelligent.applytojob.com/apply/mtmGYAhb30/HR-Generalist">
        HR Generalist                                    </a>
    </h3>
    <ul class='list-inline list-group-item-text'>
      <li><i class='fa fa-map-marker'></i>Lahore, Lahore, Pakistan</li>
    </ul>
  </li>
</ul>
"""


def test_jazzhr_board_parsing_and_states():
	result = jazzhr.parseBoardHtml(JAZZHR_PAGE, fakeJobId)
	assert result["confirmedEmpty"] is False
	assert result["jobs"][0]["id"] == "HR Generalist|mtmGYAhb30"
	assert result["jobs"][0]["location"] == "Lahore, Lahore, Pakistan"
	assert jazzhr.parseBoardHtml("<p>There are no open positions at this time.</p>", fakeJobId) == {"jobs": [], "confirmedEmpty": True}
	with pytest.raises(ValueError, match="no longer active"):
		jazzhr.parseBoardHtml("JazzHR - Inactive Career Page This account is no longer active.", fakeJobId)
	with pytest.raises(ValueError, match="layout changed"):
		jazzhr.parseBoardHtml("<html>something else</html>", fakeJobId)


def test_bamboohr_opening():
	opening = {"id": "284", "jobOpeningName": "Demand Planning & Forecasting Analyst", "departmentLabel": None,
		"employmentStatusLabel": "Full-Time - Pakistan", "location": {"city": "Lahore", "state": "Punjab"}, "atsLocation": {}, "isRemote": None}
	job = bamboohr.parseOpening(opening, "algomus", fakeJobId)
	assert job["id"] == "Demand Planning & Forecasting Analyst|284"
	assert job["link"] == "https://algomus.bamboohr.com/careers/284"
	assert job["location"] == "Lahore, Punjab"
	assert job["jobType"] == "Full-Time - Pakistan"
