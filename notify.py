from __future__ import annotations

import html
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import resend

try:
	from dotenv import load_dotenv
	load_dotenv()
except ImportError:
	pass

fromEmail = "onboarding@resend.dev"
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def getTodayDateString() -> str:
	todayString = datetime.now(timezone.utc).strftime("%Y-%m-%d")
	return todayString


def loadJsonFile(filePath: Path) -> list[dict]:
	if not filePath.exists():
		emptyList: list[dict] = []
		return emptyList

	content = filePath.read_text(encoding="utf-8")
	isEmptyContent = not content.strip()
	if isEmptyContent:
		emptyList: list[dict] = []
		return emptyList

	data = json.loads(content)
	return data


def buildJobRowHtml(job: dict) -> str:
	company = html.escape(str(job.get("company", "")))
	title = html.escape(str(job.get("title", "")))
	location = html.escape(str(job.get("location", "")))
	link = html.escape(str(job.get("link", "")), quote=True)

	rowHtml = f"<tr><td>{company}</td><td><a href=\"{link}\">{title}</a></td><td>{location}</td></tr>"
	return rowHtml


def buildErrorRowHtml(errorEntry: dict) -> str:
	company = html.escape(str(errorEntry.get("company", "")))
	failureType = html.escape(str(errorEntry.get("type", "exception")))
	reason = html.escape(str(errorEntry.get("reason", "")))
	errorMessage = html.escape(str(errorEntry.get("error", "")))
	oldJobCount = errorEntry.get("oldJobCount", "")
	newJobCount = errorEntry.get("newJobCount", "")
	jobCountText = html.escape(f"{oldJobCount} → {newJobCount}") if oldJobCount != "" else ""

	rowHtml = f"<tr><td>{company}</td><td>{failureType}</td><td>{reason}</td><td>{jobCountText}</td><td><small>{errorMessage}</small></td></tr>"
	return rowHtml


def buildEmailHtml(newJobs: list[dict], errorEntries: list[dict], runDate: str) -> str:
	jobRowsHtml = ""
	jobIndex = 0
	while jobIndex < len(newJobs):
		job = newJobs[jobIndex]
		jobRowsHtml = jobRowsHtml + buildJobRowHtml(job)
		jobIndex = jobIndex + 1

	errorRowsHtml = ""
	errorIndex = 0
	while errorIndex < len(errorEntries):
		errorEntry = errorEntries[errorIndex]
		errorRowsHtml = errorRowsHtml + buildErrorRowHtml(errorEntry)
		errorIndex = errorIndex + 1

	jobCount = len(newJobs)
	errorCount = len(errorEntries)

	hasJobs = jobCount > 0
	jobsSectionHtml = ""
	if hasJobs:
		jobsSectionHtml = f"""
		<h3>New Jobs ({jobCount})</h3>
		<table border="1" cellpadding="6" cellspacing="0">
			<tr><th>Company</th><th>Title</th><th>Location</th></tr>
			{jobRowsHtml}
		</table>
		"""
	else:
		jobsSectionHtml = "<p>No new jobs found today.</p>"

	hasErrors = errorCount > 0
	errorsSectionHtml = ""
	if hasErrors:
		errorsSectionHtml = f"""
		<h3>Scraper Errors ({errorCount})</h3>
		<table border="1" cellpadding="6" cellspacing="0">
			<tr><th>Company</th><th>Type</th><th>Reason</th><th>Jobs (before → now)</th><th>Error</th></tr>
			{errorRowsHtml}
		</table>
		"""

	bodyHtml = f"""
	<html>
	<body>
		<h2>Job Tracker Digest — {runDate}</h2>
		{jobsSectionHtml}
		{errorsSectionHtml}
	</body>
	</html>
	"""
	return bodyHtml


def buildEmailSubject(jobCount: int, errorCount: int, runDate: str) -> str:
	hasErrors = errorCount > 0
	if hasErrors:
		subject = f"Job Tracker {runDate} — {jobCount} new job(s), {errorCount} error(s)"
	else:
		subject = f"Job Tracker {runDate} — {jobCount} new job(s)"
	return subject


def sendEmail(apiKey: str, toEmail: str, subject: str, htmlBody: str) -> bool:
	resend.api_key = apiKey

	payload = {
		"from": fromEmail,
		"to": [toEmail],
		"subject": subject,
		"html": htmlBody,
	}

	try:
		response = resend.Emails.send(payload)
		emailId = response.get("id", "")
		hasEmailId = emailId != ""
		if hasEmailId:
			logger.info("Email sent successfully, id=%s", emailId)
		else:
			logger.warning("Email send returned no id, response=%s", response)
		return hasEmailId
	except Exception as error:
		logger.exception("Failed to send email: %s", error)
		return False


def main() -> None:
	apiKey = os.environ.get("RESEND_API_KEY", "")
	toEmail = os.environ.get("NOTIFY_EMAIL", "sobandegen@gmail.com")

	hasApiKey = apiKey != ""
	hasToEmail = toEmail != ""
	if not hasApiKey or not hasToEmail:
		logger.error("Missing RESEND_API_KEY or NOTIFY_EMAIL environment variable, skipping notification")
		return

	runDate = getTodayDateString()
	outputDir = Path(__file__).with_name("output")

	newJobsPath = outputDir / f"new_jobs_{runDate}.json"
	errorsPath = outputDir / f"errors_{runDate}.json"

	newJobs = loadJsonFile(newJobsPath)
	errorEntries = loadJsonFile(errorsPath)

	jobCount = len(newJobs)
	errorCount = len(errorEntries)

	hasNothingToReport = jobCount == 0 and errorCount == 0
	if hasNothingToReport:
		logger.info("No new jobs and no errors, skipping email")
		return

	subject = buildEmailSubject(jobCount, errorCount, runDate)
	htmlBody = buildEmailHtml(newJobs, errorEntries, runDate)

	sendEmail(apiKey, toEmail, subject, htmlBody)


if __name__ == "__main__":
	main()
