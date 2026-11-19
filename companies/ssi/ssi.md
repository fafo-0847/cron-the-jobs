# SSI (Strategic Systems International) — Career Page Notes

## Source

- Platform: Breezy HR (hosted ATS)
- URL: https://strategic-systems-international.breezy.hr
- Type: server-rendered HTML, Playwright required

## DOM structure

Container: `.positions-container ul.positions.location` with child `li.position` elements — one per job

Per position:
- Link: first `a` element's `href`
- Title: `h2` inner text
- Location: `.meta li.location span` inner text
- Job type: `.meta li.type span` inner text

## Known fields per job

- title
- link (relative href joined with sourceUrl)
- location (from .location span)
- jobType (from .type span)
- department — not available, left as empty string
- postedAt — not available, left as empty string
- state — always "open"

## Pagination

None visible in the sample. Single page loads all jobs. If pagination exists, it's not yet triggered.

## Sanity guard

Same as other scrapers — zero-job drop keeps old snapshot.

## Open questions

- Confirm whether the page loads all jobs on initial page load or if there's lazy-loading / pagination that needs to be triggered
