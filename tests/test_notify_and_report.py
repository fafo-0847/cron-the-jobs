import json

import failure_report
import notify


def test_error_row_escapes_html_and_shows_reason():
	entry = {"company": "mergestack", "type": "zero_jobs", "reason": "Blocked by Cloudflare bot challenge",
		"error": "Title: Just a moment... Preview: <!DOCTYPE html>", "oldJobCount": 4, "newJobCount": 0}
	rowHtml = notify.buildErrorRowHtml(entry)
	assert "&lt;!DOCTYPE html&gt;" in rowHtml
	assert "Blocked by Cloudflare" in rowHtml
	assert "4 → 0" in rowHtml


def test_error_row_handles_legacy_entries():
	rowHtml = notify.buildErrorRowHtml({"company": "x", "error": "boom", "failedAt": "t"})
	assert "<td>x</td>" in rowHtml and "boom" in rowHtml


def test_email_lists_errors():
	htmlBody = notify.buildEmailHtml([], [{"company": "a", "error": "e", "reason": "r"}], "2026-01-01")
	assert "Scraper Errors (1)" in htmlBody


def test_failure_report_counts_and_window(tmp_path):
	days = {
		"2026-01-01": [{"company": "a", "reason": "Timeout"}],
		"2026-01-02": [{"company": "a", "reason": "Timeout"}, {"company": "b", "error": "boom"}],
		"2026-01-03": [],
		"2026-01-04": [{"company": "a", "reason": "DNS"}, {"company": "a", "reason": "DNS"}],
	}
	for day, entries in days.items():
		(tmp_path / f"errors_{day}.json").write_text(json.dumps(entries))
	(tmp_path / "errors_2026-01-05.json").write_text("")

	files = failure_report.listErrorFiles(tmp_path, 4)
	assert [f.stem for f in files][0] == "errors_2026-01-02"
	rows = failure_report.buildReport(files)
	byCompany = {row["company"]: row for row in rows}
	assert byCompany["a"]["failures"] == 2
	assert byCompany["a"]["reasons"] == {"Timeout": 1, "DNS": 1}
	assert byCompany["b"]["reasons"] == {"boom": 1}
	text = failure_report.formatReport(rows, files)
	assert "a: 2/4" in text
