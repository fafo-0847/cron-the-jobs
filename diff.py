from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def extractJobIds(jobs: list[dict]) -> set[str]:
	jobIds: set[str] = set()
	jobIndex = 0
	while jobIndex < len(jobs):
		job = jobs[jobIndex]
		jobId = job.get("id", "")
		hasId = jobId != ""
		if hasId:
			jobIds.add(jobId)
		jobIndex = jobIndex + 1
	return jobIds


def findAddedJobs(oldJobs: list[dict], newJobs: list[dict]) -> list[dict]:
	oldIds = extractJobIds(oldJobs)
	newIds = extractJobIds(newJobs)
	addedIds = newIds - oldIds

	addedJobs: list[dict] = []
	newIndex = 0
	while newIndex < len(newJobs):
		job = newJobs[newIndex]
		jobId = job.get("id", "")
		isNewJob = jobId in addedIds
		if isNewJob:
			addedJobs.append(job)
		newIndex = newIndex + 1

	return addedJobs


def tagJobsWithCompany(jobs: list[dict], companyName: str) -> list[dict]:
	detectedAt = datetime.now(timezone.utc).isoformat()
	taggedJobs: list[dict] = []

	jobIndex = 0
	while jobIndex < len(jobs):
		job = jobs[jobIndex]
		taggedJob = dict(job)
		taggedJob["company"] = companyName
		taggedJob["detectedAt"] = detectedAt
		taggedJobs.append(taggedJob)
		jobIndex = jobIndex + 1

	return taggedJobs


def diffCompany(companyName: str, oldJobs: list[dict], newJobs: list[dict], isFirstRun: bool) -> list[dict]:
	oldJobCount = len(oldJobs)
	newJobCount = len(newJobs)

	suspiciousDrop = oldJobCount > 0 and newJobCount == 0
	if suspiciousDrop:
		logger.warning("Skipping diff for %s, suspicious zero-job scrape. Old=%d New=%d", companyName, oldJobCount, newJobCount)
		emptyResult: list[dict] = []
		return emptyResult

	if isFirstRun:
		logger.info("First run for %s, establishing baseline with %d jobs, no diff reported", companyName, newJobCount)
		emptyResult: list[dict] = []
		return emptyResult

	addedJobs = findAddedJobs(oldJobs, newJobs)
	taggedJobs = tagJobsWithCompany(addedJobs, companyName)

	addedCount = len(taggedJobs)
	hasNewJobs = addedCount > 0
	if hasNewJobs:
		logger.info("Found %d new job(s) for %s", addedCount, companyName)

	return taggedJobs


def getRunDate() -> str:
	runDate = datetime.now(timezone.utc).strftime("%Y-%m-%d")
	return runDate


def getBatchFilePath(outputDir: Path, runDate: str) -> Path:
	fileName = f"new_jobs_{runDate}.json"
	batchPath = outputDir / fileName
	return batchPath


def getErrorsFilePath(outputDir: Path, runDate: str) -> Path:
	fileName = f"errors_{runDate}.json"
	errorsPath = outputDir / fileName
	return errorsPath


def loadBatchFile(batchPath: Path) -> list[dict]:
	if not batchPath.exists():
		emptyBatch: list[dict] = []
		return emptyBatch

	content = batchPath.read_text(encoding="utf-8")
	isEmptyContent = not content.strip()
	if isEmptyContent:
		emptyBatch: list[dict] = []
		return emptyBatch

	data = json.loads(content)
	return data


def writeBatchFile(batchPath: Path, allEntries: list[dict]) -> None:
	batchPath.parent.mkdir(parents=True, exist_ok=True)
	output = json.dumps(allEntries, indent=2, ensure_ascii=False)
	batchPath.write_text(output + "\n", encoding="utf-8")


def appendToBatch(batchPath: Path, newEntries: list[dict]) -> list[dict]:
	hasNewEntries = len(newEntries) > 0
	if not hasNewEntries:
		existingEntries = loadBatchFile(batchPath)
		return existingEntries

	existingEntries = loadBatchFile(batchPath)
	combinedEntries = existingEntries + newEntries
	writeBatchFile(batchPath, combinedEntries)
	return combinedEntries