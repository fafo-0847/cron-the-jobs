import logging
from pathlib import Path
from typing import Any

from companies._shared import company

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("triaico")

sourceUrl = 'https://triaico.com/careers'
source = {
	"type": "html",
	"url": "https://triaico.com/careers",
	"linkPattern": "/(?:jobs?|careers?|positions?|openings?|vacanc(?:y|ies)|opportunit(?:y|ies)|job-detail)/[^/?#]*[a-z0-9][^/?#]*/?$",
	"requireJobWord": True,
	"emptyPattern": "No Jobs Available"
}
snapshotPath = Path(__file__).with_name("triaico.json")


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
