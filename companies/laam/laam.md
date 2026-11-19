# Laam — Career Page Notes

## Source

- Platform: PeopleForce (self-hosted careers page)
- URL: https://laam.peopleforce.io/careers
- Type: server-rendered HTML, no JSON API found — Playwright required

## Pagination

- Query param style: `?page=N`
- Page 1 has no query param (base URL)
- Last page number is read from `nav.pagy-bootstrap-nav .page-link` text content
- Loop from page 1 to detected last page, rebuilding URL each time

## DOM structure

Container: `#results .row.gy-3 > .col-12` — one div per job card

Per card:
- Title + link: `a.stretched-link` — `href` is relative, joined with sourceUrl
- Meta line: `.tw-text-neutral-dark-80.small` — single comma-separated string

## Meta line parsing

Format is inconsistent in field count. Observed patterns:
- `Department, JobType, Location` (3 parts) → e.g. "Engineering, Full-time, NASTP, Lahore" is actually 4 comma parts because location itself has a comma
- First part = department
- Second part = job type
- Everything after = location (joined back with ", ")

This is a heuristic, not guaranteed. If a future scrape shows a department with no job type, fields will misalign. Revisit if jobType values start looking like locations.

## Known fields per job

- title
- link
- department
- jobType
- location
- postedAt — not available on this page, left as empty string
- state — always "open" since closed jobs are not listed

## Open questions

- No "posted X days ago" timestamp visible in the sample. If found later, add extraction for it.
- Confirm whether `?page=N` works directly via URL navigation or requires clicking (data-turbo-action suggests Turbo Frame navigation — direct URL nav was not yet tested live, only assumed from anchor hrefs).
