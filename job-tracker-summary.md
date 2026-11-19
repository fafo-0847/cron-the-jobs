# Job Tracker — Living Summary

This file is the running summary for the project. Append new decisions, changes, and updates here as the build progresses.

## Current Goal

Build a daily job-tracking pipeline that:

- Scrapes 300 company career pages every day
- Uses direct ATS APIs for Greenhouse and Lever
- Uses Playwright for custom and Workday pages
- Diffs current jobs against stored snapshots
- Saves snapshots to Azure Blob Storage
- Appends new listings to a daily output file
- Sends one email notification when new jobs are found

## Project Layout

- `scraper/scrape.py` for collection logic
- `scraper/diff.py` for job comparison
- `scraper/extract.py` for parsing HTML into job objects
- `scraper/notify.py` for SendGrid email delivery
- `config/companies.json` for company definitions
- `data/snapshots/` for local snapshot cache
- `output/new_jobs.json` for daily new-job output
- `.github/workflows/daily_scrape.yml` for cron execution
- `Dockerfile` and `requirements.txt` for packaging and dependencies

## Core Data Shapes

### Company

```json
{
  "id": "company_001",
  "name": "Acme Corp",
  "careerUrl": "https://acme.com/careers",
  "atsType": "greenhouse",
  "atsSlug": "acmecorp"
}
```

### Job

```json
{
  "id": "unique_hash_of_title_plus_url",
  "title": "Software Engineer",
  "link": "https://acme.com/careers/job/123",
  "department": "Engineering",
  "location": "Lahore, Pakistan",
  "type": "Full-time",
  "scrapedAt": "2026-06-13T08:00:00Z"
}
```

### Snapshot

```json
{
  "companyId": "company_001",
  "lastScraped": "2026-06-13T08:00:00Z",
  "jobs": []
}
```

### Daily Output

```json
[
  {
    "date": "2026-06-13",
    "companyId": "company_001",
    "companyName": "Acme Corp",
    "newJobs": []
  }
]
```

## Working Rules

- One operation per line
- Named intermediary variables only
- No list comprehensions
- No lambdas
- No inline comments
- camelCase for variables and functions
- Prefer while loops when practical
- Use explicit async/await everywhere

## Runtime Rules

- Greenhouse and Lever should use API calls directly
- Custom and Workday sources should use Playwright
- Run companies in batches of 10
- Do not let one failed company stop the full run
- Treat missing old snapshots as first-run data
- Append to `output/new_jobs.json` instead of overwriting it

## Environment Variables

- `AZURE_STORAGE_CONNECTION_STRING`
- `SENDGRID_API_KEY`
- `NOTIFY_EMAIL_TO`
- `NOTIFY_EMAIL_FROM`

## Current Build Notes

- Initial summary file created from `job-tracker-codex.md`
- Local Python virtual environment created at `.venv`
- Added `.env.example` with the required runtime variables
- Added `.gitignore` entries for `.venv`, `.env`, and Python cache files
- Added Netsol-specific source notes and a scraper for the openings page
- Netsol scraper is now async, modular, and class-free
- Netsol fetch uses a stdlib request wrapped in `asyncio.to_thread`
- Future code changes and decisions should be appended below in chronological order

## Change Log

### 2026-06-13

- Created the living summary document
- Captured the project goal, layout, schemas, rules, and runtime constraints
- Set up local venv and environment scaffolding
- Refined the Netsol notes and added `companies/netsol/netsol.py`
- Switched the Netsol scraper to async modular functions without classes
- Finalized the Netsol fetch path as a class-free async wrapper around stdlib HTTP