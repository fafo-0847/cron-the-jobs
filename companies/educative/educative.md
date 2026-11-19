# Educative — Career Page Notes

## Source

- Platform: Lever (hosted ATS)
- Public API: https://api.lever.co/v0/postings/educative?mode=json
- Type: direct JSON API — no Playwright needed, no scraping required
- Original career page (for reference only, not used by scraper): https://jobs.lever.co/educative

## Why API over HTML

The HTML sample provided showed `jobs.lever.co/educative` postings, which confirms this company is on Lever. Lever exposes a public, unauthenticated JSON API for every company's postings — calling it directly is faster and far more stable than parsing HTML, since Lever's public page markup is more likely to change than their API contract.

## Response shape (per posting)

Key fields used from each posting object:
- `text` → job title
- `hostedUrl` → application link
- `categories.team` or `categories.department` → department
- `categories.location` → location
- `categories.commitment` → job type (e.g. Full-time)
- `workplaceType` → On-site / Remote / Hybrid
- `createdAt` → epoch milliseconds, converted to ISO timestamp for `postedAt`

## Known fields per job

- title
- link
- department
- location
- jobType
- workplaceType
- postedAt
- state — always "open" since Lever only lists active postings

## Pagination

None needed. The Lever API returns the full postings array in a single response, no paging required.

## Sanity guard

Same zero-job-drop guard as other scrapers: if the previous snapshot had jobs and the new fetch returns zero, the old snapshot is kept and a warning is logged instead of overwriting with an empty list.

## Open questions

- Confirm `categories.team` vs `categories.department` key name once a live response is seen — Lever boards sometimes use one or the other depending on how the company configured their board.
