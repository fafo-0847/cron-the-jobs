from __future__ import annotations

import asyncio
import importlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import diff
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


async def run_company(company_name: str, companies_dir: Path) -> list[dict]:
	module_name = f"companies.{company_name}.{company_name}"
	logger.info("Running %s", module_name)
	module = importlib.import_module(module_name)

	company_json_path = companies_dir / company_name / f"{company_name}.json"
	is_first_run = not company_json_path.exists()

	existing_snapshot = module.loadExistingSnapshot()
	state = await module.fetchState()
	new_jobs = diff.diffCompany(company_name, existing_snapshot["jobs"], state["jobs"], is_first_run)

	snapshot = module.buildSnapshot(state, existing_snapshot)
	module.writeSnapshot(snapshot)

	logger.info("Finished %s", module_name)
	return new_jobs


async def main() -> None:
	
	start_time = time.perf_counter()

	companies_dir = Path(__file__).with_name("companies")
	company_names = list(iter_company_names(companies_dir))
	if not company_names:
		logger.warning("No company scrapers found under %s", companies_dir)
		return

	batch_entries: list[dict] = []
	error_entries: list[dict] = []

	for company_name in company_names:
		try:
			new_jobs = await run_company(company_name, companies_dir)
			batch_entries.extend(new_jobs)
		except Exception as company_error:
			logger.exception("Company scraper failed: %s", company_name)
			failed_at = datetime.now(timezone.utc).isoformat()
			error_record = {
				"company": company_name,
				"error": str(company_error),
				"failedAt": failed_at,
			}
			error_entries.append(error_record)

	run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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