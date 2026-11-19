# Afiniti — Career Page Notes

## Source

- Platform: Custom HTML (table-row job listing)
- URL: https://www.afiniti.com/jobs/
- Type: server-rendered HTML, Playwright required

## DOM structure

Container: `.job_row.row` — one row per job (resembles table rows)

Per row:
- Title: `.title_mobile h7.bold` inner text
- Location: `data-location` attribute on the `.job_row` div
- Posted date: `.date` h8 inner text
- Link: `.cta-wrapper` anchor's `href`

## Known fields per job

- title
- link
- location (from data-location attribute)
- postedAt (from .date element)
- department — not available, left as empty string
- jobType — not available, left as empty string
- state — always "open"

## Pagination

None visible in the sample. Single page loads all jobs. If pagination exists, it's not yet triggered.

## Sanity guard

Same as other scrapers — zero-job drop keeps old snapshot.

## Open questions

- Confirm whether the page loads all jobs on initial page load or if there's lazy-loading / pagination that needs to be triggered
