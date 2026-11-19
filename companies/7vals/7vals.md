# 7Vals — Career Page Notes

## Source

- Platform: Custom HTML (list-group job listing)
- URL: https://7vals.simplicant.com
- Type: server-rendered HTML, Playwright required

## DOM structure

Container: `.list-group.list-jobs` with `.list-group-item` anchors — one per job

Per item:
- Link: `.list-group-item` anchor's `href` (relative, `//7vals.simplicant.com/...`)
- Title: `.list-group-item-title.job-title` inner text
- Location: `.list-group-item-subtitle.job-subtitle` inner text

## Known fields per job

- title
- link (relative href joined with sourceUrl)
- location (from .job-subtitle)
- department — not available, left as empty string
- jobType — not available, left as empty string
- postedAt — not available, left as empty string
- state — always "open"

## Pagination

None visible in the sample. Single page loads all jobs. If pagination exists, it's not yet triggered.

## Sanity guard

Same as other scrapers — zero-job drop keeps old snapshot.

## Open questions

- Confirm whether the page loads all jobs on initial page load or if there's lazy-loading that needs to be triggered
