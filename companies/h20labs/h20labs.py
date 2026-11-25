import logging
from pathlib import Path
from typing import Any

from companies._shared import company

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("h20labs")

sourceUrl = 'https://www.h2olabs.io/career'
source = {
	"type": "html",
	"url": "https://www.h2olabs.io/career",
	"linkPattern": "h2olabs\\.io/career/[a-z0-9-]+$",
	"render": True
}
snapshotPath = Path(__file__).with_name("h20labs.json")


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
