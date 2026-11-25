import logging
from pathlib import Path
from typing import Any

from companies._shared import company

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("finqalab")

sourceUrl = 'https://finqalab.com/careers/open-positions'
source = {
	"type": "html",
	"url": "https://finqalab.com/careers/open-positions",
	"render": True,
	"linkPattern": "^mailto:careers@finqalab\\.com\\?subject=",
	"titleFromParam": "subject",
	"titleStripPattern": "\\s*[–-]\\s*\\[Your Name\\]"
}
snapshotPath = Path(__file__).with_name("finqalab.json")


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
