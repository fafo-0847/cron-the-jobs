# Job Tracker — Claude Code Context

## What this project does

Scrapes 300 company career pages daily, diffs against previous state, extracts new job listings with links, saves snapshots to Azure Blob Storage, and sends new jobs via email as JSON.

---

## Project structure

```
job-tracker/
├── scraper/
│   ├── scrape.py          # Playwright scraping logic
│   ├── diff.py            # Compare old vs new listings
│   ├── extract.py         # Parse HTML into structured jobs
│   └── notify.py          # Email sender via SendGrid
├── data/
│   └── snapshots/         # Local cache of per-company JSON (also pushed to Blob)
├── config/
│   └── companies.json     # 300 companies with career page URLs + ATS type
├── output/
│   └── new_jobs.json      # Appended daily with new listings
├── .github/
│   └── workflows/
│       └── daily_scrape.yml
├── Dockerfile
├── requirements.txt
└── .env                   # Never commit this
```

---

## Tech stack

- Python 3.11
- Playwright (async, Chromium) for JS-rendered pages
- azure-storage-blob for snapshot persistence
- SendGrid for email notifications
- GitHub Actions for cron scheduling (runs daily at 08:00 UTC)
- Docker for packaging

---

## Coding style — follow strictly

- One operation per line
- Named intermediary variables, no chaining
- No list comprehensions
- No lambdas
- No inline comments
- camelCase for variables and functions
- While loops over for loops where possible
- All async functions use async/await explicitly

---

## companies.json schema

```json
[
  {
    "id": "company_001",
    "name": "Acme Corp",
    "careerUrl": "https://acme.com/careers",
    "atsType": "greenhouse",
    "atsSlug": "acmecorp"
  }
]
```

atsType values: `"greenhouse"`, `"lever"`, `"workday"`, `"custom"`

For `"greenhouse"` and `"lever"`, skip Playwright and hit their APIs directly.
For `"custom"` or `"workday"`, use Playwright.

---

## ATS API patterns (no auth needed for public boards)

Greenhouse:
```
GET https://boards-api.greenhouse.io/v1/boards/{atsSlug}/jobs
```

Lever:
```
GET https://api.lever.co/v0/postings/{atsSlug}?mode=json
```

Parse these responses directly into the job schema below. No Playwright needed.

---

## Job object schema

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

Generate `id` as `md5(title + link)` to detect duplicates reliably.

---

## Snapshot schema (one file per company in Azure Blob)

Blob path: `snapshots/company_001.json`

```json
{
  "companyId": "company_001",
  "lastScraped": "2026-06-13T08:00:00Z",
  "jobs": [ ...array of job objects... ]
}
```

---

## new_jobs.json output schema

Appended daily — do not overwrite, append new entries.

```json
[
  {
    "date": "2026-06-13",
    "companyId": "company_001",
    "companyName": "Acme Corp",
    "newJobs": [ ...array of job objects... ]
  }
]
```

---

## Azure Blob setup

Container name: `job-tracker`

Two folders inside:
- `snapshots/` — one JSON per company, updated every run
- `output/` — one JSON per day with new jobs found

Environment variables needed:
```
AZURE_STORAGE_CONNECTION_STRING=...
```

Use `azure-storage-blob` SDK. Always use async client (`BlobServiceClient`).

---

## scrape.py behavior

1. Load companies.json
2. For each company:
   - If atsType is greenhouse or lever: hit API directly, parse JSON response
   - If atsType is custom or workday: launch Playwright, navigate to careerUrl, wait for job listings to appear, extract links and titles
3. Return list of job objects per company
4. Handle timeouts gracefully — if a page fails, log it and continue, do not crash the whole run

Playwright settings:
- Headless: true
- Timeout: 30 seconds per page
- User agent: set a real browser user agent string
- Run companies in batches of 10 concurrently, not all 300 at once

---

## diff.py behavior

1. Pull old snapshot from Azure Blob for a company
2. Compare old job IDs vs new job IDs (use the md5 hash id field)
3. New jobs = IDs present in new but not in old
4. Return list of new job objects
5. If no old snapshot exists (first run), treat all current jobs as new

---

## notify.py behavior

1. Collect all new jobs across all companies
2. If zero new jobs found, do not send email
3. If new jobs found, send one email with:
   - Subject: `Job Tracker — {count} new listings found on {date}`
   - Body: JSON of the new_jobs output for that day
4. Use SendGrid Python SDK
5. Environment variable: `SENDGRID_API_KEY`, `NOTIFY_EMAIL_TO`, `NOTIFY_EMAIL_FROM`

---

## GitHub Actions workflow

File: `.github/workflows/daily_scrape.yml`

- Trigger: cron `0 8 * * *` (daily 08:00 UTC)
- Runner: ubuntu-latest
- Cache: `~/.cache/ms-playwright` keyed on `requirements.txt` hash
- Secrets needed: `AZURE_STORAGE_CONNECTION_STRING`, `SENDGRID_API_KEY`, `NOTIFY_EMAIL_TO`, `NOTIFY_EMAIL_FROM`
- Steps: checkout → cache restore → pip install → playwright install chromium → python main.py

---

## main.py entrypoint

Orchestrates in this order:
1. Load companies
2. Run scrape.py for all companies
3. For each company run diff.py against blob snapshot
4. Save updated snapshot to blob
5. Append new jobs to output/new_jobs.json and push to blob
6. Run notify.py

---

## Error handling rules

- Never let one failed company crash the full run
- Log failures with company id and error message
- At end of run print summary: X succeeded, Y failed, Z new jobs found
- Failed companies should be retried on next day's run naturally

---

## requirements.txt (baseline)

```
playwright==1.44.0
azure-storage-blob==12.19.0
sendgrid==6.11.0
python-dotenv==1.0.0
aiohttp==3.9.5
```

---

## What NOT to do

- Do not use Scrapy
- Do not use requests for JS-rendered pages
- Do not use Azure Functions, Logic Apps, or Container Apps
- Do not use ReportLab
- Do not commit .env
- Do not overwrite new_jobs.json — always append
- Do not run all 300 companies in parallel — batch of 10
