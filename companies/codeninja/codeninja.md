# CodeNinja — Career Page Notes

## Source

- Platform: Workable (hosted ATS)
- URL: https://apply.workable.com/codeninjapk
- Type: server-rendered HTML, Playwright required

## DOM structure

Container: `ul[data-ui='list']` with `li[data-ui='job']` children — one per job

Per job item:
- Link: first `a` element's `href`
- Title: `h3[data-ui='job-title'] span` inner text
- Department: `span[data-ui='job-department']` inner text
- Location: `div[data-ui='job-location']` inner text (includes city, province, country)
- Job type: `span[data-ui='job-type']` inner text
- Posted date: `small[data-ui='job-posted']` inner text (e.g. "Posted 2 days ago")

## Known fields per job

- title
- link (relative href joined with sourceUrl)
- location
- department
- jobType
- postedAt (relative date string)
- state — always "open"

## Pagination

None visible in the sample. Single page loads all jobs. If pagination exists, it's not yet triggered.

## Sanity guard

Same as other scrapers — zero-job drop keeps old snapshot.

## Open questions

- Confirm whether the page loads all jobs on initial page load or if there's lazy-loading / pagination that needs to be triggered
