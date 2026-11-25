"""Create or update a config-driven company scraper.

Usage:
  python tools/new_company.py <folder> <careersUrl> '<source json>' [--force]

Example:
  python tools/new_company.py emumba https://www.emumba.com/open-positions/ '{"type": "greenhouse", "slug": "emumba"}'

Writes companies/<folder>/<folder>.py using companies/_shared/company.py. Refuses to
overwrite an existing hand-written scraper unless --force is given.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

repoRoot = Path(__file__).resolve().parent.parent
template = '''import logging
from pathlib import Path
from typing import Any

from companies._shared import company

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("{folder}")

sourceUrl = {sourceUrl!r}
source = {source}
snapshotPath = Path(__file__).with_name("{folder}.json")


async def fetchState(url: str = sourceUrl) -> dict[str, Any]:
	return await company.fetchState(source, logger)


def loadExistingSnapshot() -> dict[str, Any]:
	return company.loadSnapshot(snapshotPath, sourceUrl)


def buildSnapshot(state: dict, existingSnapshot: dict) -> dict:
	return company.buildSnapshot(state, existingSnapshot, sourceUrl, logger)


def writeSnapshot(snapshot: dict) -> None:
	company.writeSnapshot(snapshotPath, snapshot)


if __name__ == "__main__":
	import asyncio

	fetched = asyncio.run(fetchState())
	print(len(fetched["jobs"]), "jobs", [job["title"] for job in fetched["jobs"][:5]])
'''
configMarker = "from companies._shared import company"


def formatSource(source: dict) -> str:
	return json.dumps(source, indent="\t", ensure_ascii=False).replace("true", "True").replace("false", "False").replace("null", "None")


def writeCompany(folder: str, sourceUrl: str, source: dict, force: bool = False) -> Path:
	modulePath = repoRoot / "companies" / folder / f"{folder}.py"
	if modulePath.exists() and configMarker not in modulePath.read_text(encoding="utf-8") and not force:
		raise SystemExit(f"{modulePath} is a hand-written scraper; pass --force to replace it")
	modulePath.parent.mkdir(parents=True, exist_ok=True)
	modulePath.write_text(template.format(folder=folder, sourceUrl=sourceUrl, source=formatSource(source)), encoding="utf-8")
	return modulePath


if __name__ == "__main__":
	arguments = [argument for argument in sys.argv[1:] if argument != "--force"]
	if len(arguments) != 3:
		raise SystemExit(__doc__)
	print(writeCompany(arguments[0], arguments[1], json.loads(arguments[2]), "--force" in sys.argv))
