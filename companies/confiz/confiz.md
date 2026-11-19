# Confiz — Career Page Notes

## Source

- Platform: Custom HTML (list-group job listing)
- URL: https://confiz.simplicant.com/?country=PK
- Type: server-rendered HTML, Playwright required

## DOM structure

Container: `.list-group.list-jobs` with child `.list-group-item` anchors — one per job

Per item:
- Link: `.list-group-item` anchor's `href` (relative, `//confiz.simplicant.com/...`)
- Title: `.list-group-item-title.job-title` inner text
- Department: `.list-group-item-subtitle.job-subtitle` inner text

## Known fields per job

- title
- link (relative href joined with sourceUrl)
- department (from .job-subtitle)
- location — not available, left as empty string
- jobType — not available, left as empty string
- postedAt — not available, left as empty string
- state — always "open"

## Pagination

None visible in the sample. Single page loads all jobs. If pagination exists, it's not yet triggered.

## Sanity guard

Same as other scrapers — zero-job drop keeps old snapshot.

## Open questions

- Confirm whether the page loads all jobs on initial page load or if there's lazy-loading that needs to be triggered
