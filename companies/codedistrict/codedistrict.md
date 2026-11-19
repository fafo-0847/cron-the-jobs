# CodeDistrict — Career Page Notes

## Source

- Platform: Custom HTML (tab-based job listing)
- URL: https://codedistrict.com/careers
- Type: server-rendered HTML with multiple category tabs, Playwright required

## DOM structure

Container: `.thm-card` — one card per job, but jobs appear in multiple tabs (All Vacancies, Engineering, Sales, etc.)

Per card:
- Link: `a.stretched-link` first element's `href`
- Title: `h3` inner text
- Location: `p` inner text (contains icon HTML which is stripped by inner_text)

## Deduplication

Jobs appear across multiple tabs (e.g. "DevOps Engineer" is in both "All Vacancies" and "Engineering"). The scraper uses `md5(title + link)` to deduplicate — only the first occurrence is kept, subsequent duplicates are skipped.

## Known fields per job

- title
- link
- location
- department — not available on this page, left as empty string
- jobType — not available on this page, left as empty string
- postedAt — not available on this page, left as empty string
- state — always "open"

## Pagination

None visible. All jobs are loaded on initial page load across all tabs.

## Sanity guard

Same as other scrapers — zero-job drop keeps old snapshot.

## Open questions

- Confirm whether tabs require clicking to load their content, or if all tabs' jobs are in the DOM on initial page load (sample suggests all jobs are already present in the HTML, no tab-click loading needed, but worth verifying live)
