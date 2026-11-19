# ProgrammersForce — Career Page Notes

## Source

- Platform: Custom HTML (job-box listing)
- URL: https://programmersforce.com/apply-now/
- Type: server-rendered HTML, Playwright required

## DOM structure

Container: `.job-box-container` — one per job

Per container:
- Title: `.job-title` inner text
- Location: `.location` inner text
- Job type: `.onsite_box` inner text (e.g. "Remote", "On-site")
- Link: `a.jobs-head` href (absolute, points to apply.workable.com)

## Known fields per job

- title
- link (absolute href, typically to Workable apply flow)
- location
- jobType (Remote or On-site)
- department — not available, left as empty string
- postedAt — not available, left as empty string
- state — always "open"

## Pagination

None visible in the sample. Single page loads all jobs. If pagination exists, it's not yet triggered.

## Sanity guard

Same as other scrapers — zero-job drop keeps old snapshot.

## Open questions

- Confirm whether the page loads all jobs on initial page load or if there's lazy-loading / pagination that needs to be triggered
