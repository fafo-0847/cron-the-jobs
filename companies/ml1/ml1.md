# ML1 — Career Page Notes

## Source

- Platform: Simple Jobs Board (custom listing)
- URL: https://ml1.ai/careers/
- Type: server-rendered HTML, Playwright required
- Jobs listed in `.sjb-without-logo` containers

## DOM structure

Container: `.sjb-without-logo` — one per job

Per container:
- Link: `a.cb-demo-item` href (absolute)
- Title: `.job-title` inner text
- Date: `.job-date` inner text (relative, e.g. "Posted 4 years ago")

## Known Fields per Job

- title
- link (absolute href)
- postedAt (relative date string from .job-date, not currently extracted)
- location — not available, left as empty string
- department — not available, left as empty string
- jobType — not available, left as empty string
- state — always "open"

## Pagination

None visible in the sample. Single page loads all jobs. If pagination exists, it's not yet triggered.

## Sanity Guard

Same as other scrapers — zero-job drop keeps old snapshot.

## Open Questions

- Confirm whether the page loads all jobs on initial page load or if there's lazy-loading / pagination that needs to be triggered
- Posted date is available in DOM (.job-date) but currently not parsed; can be added if needed
