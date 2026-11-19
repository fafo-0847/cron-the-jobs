# TKXEL — Career Page Notes

## Source

- Platform: Custom HTML (single-page job listing, pagination ignored)
- URL: https://careers.tkxel.com/jobs/
- Type: server-rendered HTML, Playwright required

## DOM structure

Container: `.jobs-cards-wrp .job-card:visible` — only visible cards on initial page load

Per card:
- Link: `a` first element's `href`
- Title: `.job-title h6` inner text
- Location: `.job-location p` inner text

## Pagination

Ignored. The page has pagination buttons but the scraper only extracts the first page of visible job cards. If full coverage of all 29 vacancies is needed, pagination will need to be re-enabled.

## Known fields per job

- title
- link
- location
- department — not available, left as empty string
- jobType — not available, left as empty string
- postedAt — not available, left as empty string
- state — always "open"

## Sanity guard

Same as other scrapers — zero-job drop keeps old snapshot.

## Notes

All `.job-card` elements are captured, including those with `style="display: none"`. This means all 29 vacancies are extracted regardless of visibility state.
