import asyncio
import json
import logging
import sys
import types
from pathlib import Path

import pytest

import main
import health


def makeModule(tmpPath: Path, name: str, oldJobs: list[dict], newJobs: list[dict], snapshotFile: str | None = None, raiseError: Exception | None = None, logError: str = ""):
	module = types.ModuleType(name)
	companyLogger = logging.getLogger(name)
	snapshotPath = tmpPath / name / (snapshotFile or f"{name}.json")
	snapshotPath.parent.mkdir(parents=True, exist_ok=True)
	if oldJobs is not None:
		snapshotPath.write_text(json.dumps({"jobs": oldJobs}))
	module.snapshotPath = snapshotPath
	module.written = []

	def loadExistingSnapshot():
		if snapshotPath.exists():
			return json.loads(snapshotPath.read_text())
		return {"jobs": []}

	async def fetchState():
		if logError:
			companyLogger.error(logError)
		if raiseError is not None:
			raise raiseError
		return {"jobs": newJobs}

	def buildSnapshot(state, existing):
		if existing["jobs"] and not state["jobs"]:
			return existing
		return {"jobs": state["jobs"]}

	module.loadExistingSnapshot = loadExistingSnapshot
	module.fetchState = fetchState
	module.buildSnapshot = buildSnapshot
	module.writeSnapshot = lambda snapshot: module.written.append(snapshot)
	return module


@pytest.fixture
def registerModule(monkeypatch):
	def register(name, module):
		monkeypatch.setitem(sys.modules, f"companies.{name}.{name}", module)
	return register


def runCompany(name, tmpPath):
	collector = health.CompanyLogCollector()
	rootLogger = logging.getLogger()
	rootLogger.addHandler(collector)
	try:
		return asyncio.run(main.run_company(name, tmpPath, collector))
	finally:
		rootLogger.removeHandler(collector)


def test_new_jobs_reported_when_snapshot_file_name_differs_from_folder(tmp_path, registerModule):
	oldJobs = [{"id": "a", "title": "A"}]
	newJobs = [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]
	module = makeModule(tmp_path, "phaedra", oldJobs, newJobs, snapshotFile="phaedrasolutions.json")
	registerModule("phaedra", module)
	addedJobs, errorEntry = runCompany("phaedra", tmp_path)
	assert [job["id"] for job in addedJobs] == ["b"]
	assert errorEntry is None


def test_silent_zero_job_scrape_becomes_error_entry(tmp_path, registerModule):
	module = makeModule(tmp_path, "tkxel", [{"id": "a"}], [], logError="tkxel: wait_for_selector: Timeout 20000ms exceeded.")
	registerModule("tkxel", module)
	addedJobs, errorEntry = runCompany("tkxel", tmp_path)
	assert addedJobs == []
	assert errorEntry["type"] == "zero_jobs"
	assert errorEntry["company"] == "tkxel"


def test_main_writes_errors_file_and_survives_exceptions(tmp_path, monkeypatch, registerModule):
	companiesDir = tmp_path / "companies"
	for name in ["good", "broken", "crash"]:
		(companiesDir / name).mkdir(parents=True)
		(companiesDir / name / f"{name}.py").write_text("")
	registerModule("good", makeModule(companiesDir, "good", [{"id": "a"}], [{"id": "a"}, {"id": "n"}]))
	registerModule("broken", makeModule(companiesDir, "broken", [{"id": "a"}], []))
	registerModule("crash", makeModule(companiesDir, "crash", None, [], raiseError=RuntimeError("kaboom")))

	fakeMainFile = tmp_path / "main.py"
	monkeypatch.setattr(main, "__file__", str(fakeMainFile))
	monkeypatch.setattr(main.diff, "getRunDate", lambda: "2026-01-01")
	asyncio.run(main.main())

	errors = json.loads((tmp_path / "output" / "errors_2026-01-01.json").read_text())
	newJobs = json.loads((tmp_path / "output" / "new_jobs_2026-01-01.json").read_text())
	assert {entry["company"]: entry["type"] for entry in errors} == {"broken": "zero_jobs", "crash": "exception"}
	assert [job["id"] for job in newJobs] == ["n"]
	assert not any(isinstance(h, health.CompanyLogCollector) for h in logging.getLogger().handlers)


def test_confirmed_empty_board_clears_snapshot_without_error(tmp_path, registerModule):
	module = makeModule(tmp_path, "noon", [{"id": "a"}, {"id": "b"}], [])
	originalFetch = module.fetchState

	async def fetchConfirmedEmpty():
		state = await originalFetch()
		state["confirmedEmpty"] = True
		return state

	module.fetchState = fetchConfirmedEmpty
	registerModule("noon", module)
	addedJobs, errorEntry = runCompany("noon", tmp_path)
	assert addedJobs == []
	assert errorEntry is None
	assert module.written[-1]["jobs"] == []


def test_confirmed_empty_ignored_when_jobs_returned(tmp_path, registerModule):
	module = makeModule(tmp_path, "mixed", [{"id": "a"}], [{"id": "a"}, {"id": "c"}])
	originalFetch = module.fetchState

	async def fetchWithFlag():
		state = await originalFetch()
		state["confirmedEmpty"] = True
		return state

	module.fetchState = fetchWithFlag
	registerModule("mixed", module)
	addedJobs, errorEntry = runCompany("mixed", tmp_path)
	assert [job["id"] for job in addedJobs] == ["c"]
	assert errorEntry is None
