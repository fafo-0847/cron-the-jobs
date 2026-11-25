import logging
from pathlib import Path
from typing import Any

from companies._shared import company

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("unilever")

sourceUrl = 'https://careers.unilever.com/en/location/lahore-jobs/34155/1168579-1167710-1172451/4'
source = {
	"type": "workday",
	"url": "https://unilever.wd3.myworkdayjobs.com/Unilever_Experienced_Professionals",
	"searchText": "Pakistan",
	"locationFilter": "Pakistan|Karachi|Lahore|Islamabad|Rawalpindi|Faisalabad|Multan|Peshawar|Blue Area|Rahim Yar Khan|Sheikhupura|Khanpur"
}
snapshotPath = Path(__file__).with_name("unilever.json")


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
