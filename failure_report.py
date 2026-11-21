"""Summarise scraper failures across the most recent runs.

Usage: python failure_report.py [runs]    (default: last 30 runs)
Reads output/errors_YYYY-MM-DD.json files (one per run) written by main.py.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

defaultRunCount = 30


def listErrorFiles(outputDir: Path, runCount: int) -> list[Path]:
	allFiles = sorted(outputDir.glob("errors_*.json"))
	recentFiles = allFiles[-runCount:] if runCount > 0 else allFiles
	return recentFiles


def loadEntries(errorsPath: Path) -> list[dict]:
	content = errorsPath.read_text(encoding="utf-8").strip()
	if content == "":
		return []
	data = json.loads(content)
	isList = isinstance(data, list)
	return data if isList else []


def runDateFromPath(errorsPath: Path) -> str:
	runDate = errorsPath.stem.replace("errors_", "")
	return runDate


def buildReport(errorFiles: list[Path]) -> list[dict]:
	failureCounts: Counter = Counter()
	reasonCounts: dict[str, Counter] = defaultdict(Counter)
	runDates: dict[str, list[str]] = defaultdict(list)

	for errorsPath in errorFiles:
		runDate = runDateFromPath(errorsPath)
		seenThisRun: set[str] = set()
		for entry in loadEntries(errorsPath):
			company = entry.get("company", "unknown")
			if company in seenThisRun:
				continue
			seenThisRun.add(company)
			reason = entry.get("reason") or entry.get("error", "")
			failureCounts[company] += 1
			reasonCounts[company][reason] += 1
			runDates[company].append(runDate)

	rows: list[dict] = []
	for company, failureCount in failureCounts.most_common():
		row = {
			"company": company,
			"failures": failureCount,
			"runs": len(errorFiles),
			"firstFailed": runDates[company][0],
			"lastFailed": runDates[company][-1],
			"reasons": dict(reasonCounts[company].most_common()),
		}
		rows.append(row)
	return rows


def formatReport(rows: list[dict], errorFiles: list[Path]) -> str:
	if len(errorFiles) == 0:
		return "No errors_*.json files found."
	firstDate = runDateFromPath(errorFiles[0])
	lastDate = runDateFromPath(errorFiles[-1])
	lines = [f"Scraper failures over {len(errorFiles)} run(s), {firstDate} .. {lastDate}"]
	if len(rows) == 0:
		lines.append("No failures recorded.")
		return "\n".join(lines)
	lines.append(f"{len(rows)} company(ies) failed at least once\n")
	for row in rows:
		lines.append(f"{row['company']}: {row['failures']}/{row['runs']} (last {row['lastFailed']})")
		for reason, count in row["reasons"].items():
			lines.append(f"    {count}x {reason}")
	return "\n".join(lines)


def main() -> None:
	runCount = int(sys.argv[1]) if len(sys.argv) > 1 else defaultRunCount
	outputDir = Path(__file__).with_name("output")
	errorFiles = listErrorFiles(outputDir, runCount)
	rows = buildReport(errorFiles)
	print(formatReport(rows, errorFiles))


if __name__ == "__main__":
	main()
