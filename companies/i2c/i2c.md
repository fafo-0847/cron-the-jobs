# i2c — Career Page Notes

## Source

- Platform: Custom HTML (job listing page)
- URL: https://careers.i2cinc.com/careers/
- Type: server-rendered HTML, Playwright required
- Link format: relative paths via `index.php/showjob/...`

## DOM structure

Container: `.joblistingsInside .job-tile article.joblisting-box` — one article per job

Per article:
- Link: `article > a` first element's `href` (relative, joined with sourceUrl)
- Title: `article h2.text-xl` inner text
- Department: `article .joblisting-dept` inner text
- Location: `article .joblisting-location` inner text

## Known fields per job

- title
- link (relative href joined with sourceUrl)
- department (from .joblisting-dept)
- location (from .joblisting-location)
- jobType — not available on this page, left as empty string
- postedAt — not available on this page, left as empty string
- state — always "open"

## Pagination

None visible in the sample. Single page loads all job listings. If there's pagination (e.g. "Load More" button), it's not triggered yet.

## Sanity guard

Same as other scrapers — zero-job drop keeps old snapshot.

## Open questions

- Confirm the page loads all jobs on initial load or if there's lazy-loading / pagination that needs button clicks or scroll triggers
- `.joblisting-openings` contains a badge (e.g. "1 Position") — not currently parsed, but available if needed later
