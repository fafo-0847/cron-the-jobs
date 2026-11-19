# ConradLabs — Career Page Notes

## Source

- Platform: Custom HTML (grid-based job listing)
- URL: https://conradlabs.com/careers
- Type: server-rendered HTML, Playwright required

## DOM structure

Container: `.awsm-job-listing-item.awsm-grid-item` — one item per job

Per item:
- Link: `.awsm-job-item` anchor's `href`
- Title: `.awsm-job-post-title` inner text
- Locations: multiple `.awsm-job-specification-term` spans under `.awsm-job-specification-job-location` — joined with ", "

## Multi-location handling

Jobs can have multiple locations (e.g. "Karachi, Lahore"). All location terms are extracted and joined into a single `location` field.

## Known fields per job

- title
- link
- location (multiple locations joined with ", ")
- department — not available, left as empty string
- jobType — not available, left as empty string
- postedAt — not available, left as empty string
- state — always "open"

## Pagination

None visible in the sample. Single page loads all jobs. If pagination exists, it's not yet triggered.

## Sanity guard

Same as other scrapers — zero-job drop keeps old snapshot.

## Open questions

- Confirm whether the page loads all jobs on initial page load or if there's lazy-loading / pagination that needs to be triggered
