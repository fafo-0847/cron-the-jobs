from __future__ import annotations

import asyncio
import importlib
import logging
from pathlib import Path
from typing import Iterable

import diff
import health
import time



logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


def iter_company_names(companies_dir: Path) -> Iterable[str]:
	for entry in sorted(companies_dir.iterdir()):
		if not entry.is_dir():
			continue
		module_path = entry / f"{entry.name}.py"
		if module_path.exists():
			yield entry.name


def resolve_snapshot_path(module, company_name: str, companies_dir: Path) -> Path:
	# Some scrapers store their snapshot under a different file name than the folder
	# (e.g. phaedra/phaedrasolutions.json). Use the module's own path when it has one,
	# otherwise every run would look like a first run and new jobs would never be reported.
	module_snapshot_path = getattr(module, "snapshotPath", None)
	if module_snapshot_path is not None:
		return Path(module_snapshot_path)
	return companies_dir / company_name / f"{company_name}.json"


async def run_company(company_name: str, companies_dir: Path, collector: health.CompanyLogCollector) -> tuple[list[dict], dict | None]:
	module_name = f"companies.{company_name}.{company_name}"
	logger.info("Running %s", module_name)
	module = importlib.import_module(module_name)

	company_json_path = resolve_snapshot_path(module, company_name, companies_dir)
	is_first_run = not company_json_path.exists()

	existing_snapshot = module.loadExistingSnapshot()
	state = await module.fetchState()
	old_jobs = existing_snapshot.get("jobs", [])
	new_jobs_state = state.get("jobs", [])
	# A scraper sets confirmedEmpty when the source answered correctly and really lists
	# no openings (e.g. an ATS API returning an empty list). Then the old jobs are closed,
	# not a failed scrape, so the snapshot is cleared instead of kept.
	is_confirmed_empty = bool(state.get("confirmedEmpty")) and len(new_jobs_state) == 0
	if is_confirmed_empty:
		logger.info("%s: source confirmed 0 open jobs, clearing %d old job(s)", company_name, len(old_jobs))
		new_jobs = []
		snapshot = module.buildSnapshot(state, {"jobs": []})
	else:
		new_jobs = diff.diffCompany(company_name, old_jobs, new_jobs_state, is_first_run)
		snapshot = module.buildSnapshot(state, existing_snapshot)
	module.writeSnapshot(snapshot)

	old_job_count_for_health = 0 if is_confirmed_empty else len(old_jobs)
	error_entry = health.classifyCompanyRun(company_name, old_job_count_for_health, len(new_jobs_state), collector.records)

	logger.info("Finished %s", module_name)
	return new_jobs, error_entry


async def main() -> None:

	start_time = time.perf_counter()

	companies_dir = Path(__file__).with_name("companies")
	company_names = list(iter_company_names(companies_dir))
	if not company_names:
		logger.warning("No company scrapers found under %s", companies_dir)
		return

	batch_entries: list[dict] = []
	error_entries: list[dict] = []

	collector = health.CompanyLogCollector()
	root_logger = logging.getLogger()
	root_logger.addHandler(collector)

	try:
		for company_name in company_names:
			collector.reset()
			try:
				new_jobs, error_entry = await run_company(company_name, companies_dir, collector)
				batch_entries.extend(new_jobs)
			except Exception as company_error:
				error_entry = health.classifyCompanyRun(company_name, 0, 0, collector.records, company_error)
				logger.exception("Company scraper failed: %s", company_name)
			if error_entry is not None:
				logger.warning("Health: %s %s - %s", company_name, error_entry["type"], error_entry["reason"])
				error_entries.append(error_entry)
	finally:
		root_logger.removeHandler(collector)

	run_date = diff.getRunDate()
	output_dir = Path(__file__).with_name("output")

	batch_path = diff.getBatchFilePath(output_dir, run_date)
	diff.writeBatchFile(batch_path, batch_entries)
	logger.info("Wrote %d new job(s) to %s", len(batch_entries), batch_path)

	errors_path = diff.getErrorsFilePath(output_dir, run_date)
	diff.writeBatchFile(errors_path, error_entries)
	logger.info("Wrote %d error(s) to %s", len(error_entries), errors_path)

	end_time = time.perf_counter()

	execution_time = end_time - start_time

	print(f"Execution time: {execution_time:.6f} seconds")


if __name__ == "__main__":
	asyncio.run(main())
