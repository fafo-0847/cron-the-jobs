# Folio3 — Career Page Notes

## Source

- Platform: Custom HTML (accordion-based job listing page)
- URL: https://folio3.com/careers/
- Type: server-rendered HTML, Playwright required
- Data is in HTML attributes, not in text content — no text parsing needed

## DOM structure

Container: `.jobs-section-accordion .jobs-box.acc__card` — one div per job

Per card, all data comes from HTML attributes on the `.jobs-box` element:
- `data-title` → job title
- `data-division` → department
- `data-location` → location
- `data-type` → job type (e.g. "Regular", "Contractual")
- `data-remote` — boolean, not currently used

Inside each card:
- Apply link: first `<a>` tag's `href`

## Known fields per job

- title (from data-title)
- link (relative href, joined with sourceUrl)
- department (data-division)
- location (data-location)
- jobType (data-type)
- postedAt — not available on this page, left as empty string
- state — always "open"

## Pagination

None visible in the sample. Single page loads all job cards. If pagination exists (e.g. "Load More" button or `?page=N`), it's not triggered yet.

## Sanity guard

Same as other scrapers — zero-job drop keeps old snapshot.

## Open questions

- Confirm whether the page loads all jobs on initial load or if there's lazy-loading / pagination that needs to be triggered (page.wait_for_selector should catch everything loaded, but worth verifying)
- Verify that `data-remote="false"` jobs are the only ones shown, or if remote positions exist and are being filtered out by the page itself
