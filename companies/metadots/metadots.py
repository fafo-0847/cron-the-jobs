import logging
from pathlib import Path
from typing import Any

from companies._shared import company

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("metadots")

sourceUrl = 'https://metadots.co/careers'
source = {
	"type": "jsonapi",
	"url": "https://metadots.co/api/jobs",
	"itemsPath": "jobs",
	"fields": {
		"id": "_id",
		"jobType": "type"
	},
	"linkTemplate": "https://metadots.co/careers#{slug}"
}
snapshotPath = Path(__file__).with_name("metadots.json")


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
