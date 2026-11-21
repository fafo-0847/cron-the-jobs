from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

maxDetailMessages = 5
maxMessageLength = 300

failureTypeException = "exception"
failureTypeZeroJobs = "zero_jobs"
failureTypeErrorNoJobs = "error_no_jobs"
failureTypePartial = "partial_error"

reasonPatterns: list[tuple[str, str]] = [
	(r"Just a moment|cf-chl|challenge-platform", "Blocked by Cloudflare bot challenge"),
	(r"ERR_NAME_NOT_RESOLVED|Name or service not known|getaddrinfo failed", "Domain does not resolve (DNS)"),
	(r"ERR_HTTP2_PROTOCOL_ERROR", "HTTP2 protocol error (often bot protection)"),
	(r"ERR_CONNECTION_REFUSED|ERR_CONNECTION_RESET|ERR_CONNECTION_CLOSED|ERR_TUNNEL_CONNECTION_FAILED", "Connection refused or reset"),
	(r"\b401\b|Unauthorized", "HTTP 401 Unauthorized (API key or token rejected)"),
	(r"\b403\b|Forbidden", "HTTP 403 Forbidden (blocked)"),
	(r"\b404\b|Not Found", "HTTP 404 Not Found (page or endpoint moved)"),
	(r"(?:status|HTTP|code|error)[ =:]*5\d\d\b|\b5\d\d, message=", "HTTP 5xx server error"),
	(r"JSONDecodeError|Expecting value|ContentTypeError", "Response was not valid JSON"),
	(r"wait_for_selector|Timeout \d+ms|timed out|timeout", "Timed out waiting for job listings (page layout may have changed)"),
]


class CompanyLogCollector(logging.Handler):
	"""Collects WARNING+ log records emitted while one company scraper runs."""

	def __init__(self) -> None:
		super().__init__(level=logging.WARNING)
		self.records: list[logging.LogRecord] = []

	def emit(self, record: logging.LogRecord) -> None:
		self.records.append(record)

	def reset(self) -> None:
		self.records = []


def formatRecordMessage(record: logging.LogRecord) -> str:
	try:
		message = record.getMessage()
	except Exception:
		message = str(record.msg)
	firstLine = message.strip().splitlines()[0] if message.strip() else ""
	collapsed = re.sub(r"\s+", " ", firstLine)
	trimmed = collapsed[:maxMessageLength]
	return trimmed


def isDiffBookkeepingMessage(message: str) -> bool:
	isSuspiciousNotice = "suspicious zero-job scrape" in message
	return isSuspiciousNotice


def extractMessages(records: list[logging.LogRecord], minLevel: int) -> list[str]:
	messages: list[str] = []
	for record in records:
		isAtLevel = record.levelno >= minLevel
		if not isAtLevel:
			continue
		message = formatRecordMessage(record)
		if message == "" or isDiffBookkeepingMessage(message):
			continue
		if message not in messages:
			messages.append(message)
	return messages


def summarizeReason(messages: list[str]) -> str:
	joined = " | ".join(messages)
	for pattern, label in reasonPatterns:
		isMatch = re.search(pattern, joined, flags=re.IGNORECASE) is not None
		if isMatch:
			return label
	hasMessages = len(messages) > 0
	if hasMessages:
		return messages[0]
	return "Scraper returned 0 jobs without logging an error (selectors or API shape likely changed)"


def classifyCompanyRun(
	companyName: str,
	oldJobCount: int,
	newJobCount: int,
	records: list[logging.LogRecord],
	exception: BaseException | None = None,
) -> dict | None:
	"""Returns an error entry when a company run looks broken, otherwise None.

	- exception: the scraper raised out of main.py
	- zero_jobs: had jobs before, got 0 now (old snapshot is kept, so this was silent before)
	- error_no_jobs: got 0 jobs and logged an ERROR (scraper never worked or is broken)
	- partial_error: got jobs but also logged an ERROR (e.g. one page of several failed)
	"""
	errorMessages = extractMessages(records, logging.ERROR)
	warningMessages = extractMessages(records, logging.WARNING)

	failureType = ""
	if exception is not None:
		failureType = failureTypeException
		exceptionMessage = re.sub(r"\s+", " ", str(exception))[:maxMessageLength]
		errorMessages = [f"{type(exception).__name__}: {exceptionMessage}"] + errorMessages
	elif newJobCount == 0 and oldJobCount > 0:
		failureType = failureTypeZeroJobs
	elif newJobCount == 0 and len(errorMessages) > 0:
		failureType = failureTypeErrorNoJobs
	elif newJobCount > 0 and len(errorMessages) > 0:
		failureType = failureTypePartial

	if failureType == "":
		return None

	detailMessages = errorMessages if len(errorMessages) > 0 else warningMessages
	detailMessages = detailMessages[:maxDetailMessages]
	reason = summarizeReason(detailMessages)
	hasDetails = len(detailMessages) > 0
	errorText = detailMessages[0] if hasDetails else reason

	entry = {
		"company": companyName,
		"type": failureType,
		"reason": reason,
		"error": errorText,
		"details": detailMessages,
		"oldJobCount": oldJobCount,
		"newJobCount": newJobCount,
		"failedAt": datetime.now(timezone.utc).isoformat(),
	}
	return entry
