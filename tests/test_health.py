import logging

import health


def makeRecord(level: int, message: str, name: str = "scraper") -> logging.LogRecord:
	return logging.LogRecord(name, level, __file__, 1, message, None, None)


def test_healthy_run_returns_none():
	records = [makeRecord(logging.WARNING, "Timed out waiting for page content to update")]
	assert health.classifyCompanyRun("contour", 12, 12, records) is None


def test_zero_jobs_after_having_jobs_is_reported():
	records = [
		makeRecord(logging.ERROR, "algo: fetchState failed: Page.wait_for_selector: Timeout 20000ms exceeded."),
		makeRecord(logging.WARNING, "Skipping diff for algo, suspicious zero-job scrape. Old=2 New=0"),
	]
	entry = health.classifyCompanyRun("algo", 2, 0, records)
	assert entry["type"] == "zero_jobs"
	assert entry["oldJobCount"] == 2 and entry["newJobCount"] == 0
	assert "Timed out" in entry["reason"]
	assert all("suspicious" not in detail for detail in entry["details"])


def test_silent_zero_jobs_gets_selector_reason():
	entry = health.classifyCompanyRun("tps", 17, 0, [])
	assert entry["type"] == "zero_jobs"
	assert "without logging an error" in entry["reason"]


def test_never_worked_with_error_is_reported():
	records = [makeRecord(logging.ERROR, "zones: fetchState failed: Page.wait_for_selector: Timeout 20000ms exceeded.")]
	entry = health.classifyCompanyRun("zones", 0, 0, records)
	assert entry["type"] == "error_no_jobs"


def test_zero_jobs_without_error_and_no_history_is_not_reported():
	assert health.classifyCompanyRun("quietco", 0, 0, []) is None


def test_partial_error_when_jobs_found_but_error_logged():
	records = [makeRecord(logging.ERROR, "page 2 failed: 500, message='Internal Server Error'")]
	entry = health.classifyCompanyRun("multi", 3, 5, records)
	assert entry["type"] == "partial_error"
	assert entry["reason"] == "HTTP 5xx server error"


def test_exception_is_reported_with_type_name():
	entry = health.classifyCompanyRun("boom", 0, 0, [], ValueError("bad shape"))
	assert entry["type"] == "exception"
	assert entry["error"] == "ValueError: bad shape"


def test_reason_classification():
	cases = {
		"mergestack: a.job-row not found. Title: Just a moment...": "Cloudflare",
		"Page.goto: net::ERR_NAME_NOT_RESOLVED at https://careers.qbatch.com/jobs": "DNS",
		"API returned status 401": "401",
		"404, message='Not Found', url='https://x/api/getJobs'": "404",
		"Failed to fetch xgrid jobs: Expecting value: line 1 column 1 (char 0)": "JSON",
		"Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR at https://careers.cinnova.pk/": "HTTP2",
	}
	for message, expected in cases.items():
		assert expected in health.summarizeReason([message]), message


def test_timeout_milliseconds_not_mistaken_for_5xx():
	assert "Timed out" in health.summarizeReason(["Timeout 500ms exceeded"])


def test_collector_collects_only_warning_and_above():
	collector = health.CompanyLogCollector()
	testLogger = logging.getLogger("collector-test")
	testLogger.addHandler(collector)
	try:
		testLogger.info("ignored")
		testLogger.warning("kept")
		testLogger.error("kept too")
	finally:
		testLogger.removeHandler(collector)
	assert [record.getMessage() for record in collector.records] == ["kept", "kept too"]
	collector.reset()
	assert collector.records == []
