import logging
from pathlib import Path
from typing import Any

from companies._shared import company

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ibm")

sourceUrl = 'https://www.ibm.com/careers/search?field_keyword_05[0]=Pakistan'
source = {
	"type": "html",
	"url": "https://www.ibm.com/careers/search?field_keyword_05[0]=Pakistan",
	"render": True,
	"waitFor": "a[href*='JobDetail']",
	"linkPattern": "careers\\.ibm\\.com/.*JobDetail\\?jobId=\\d+",
	"titleSelector": ".bx--card__heading",
	"locationSelector": ".ibm--card__copy__inner",
	"departmentSelector": ".bx--card__eyebrow"
}
snapshotPath = Path(__file__).with_name("ibm.json")


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
