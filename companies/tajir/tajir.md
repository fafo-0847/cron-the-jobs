# Tajir — Career Page Notes

## Source

- Platform: Ashby (hosted ATS)
- URL: https://jobs.ashbyhq.com/tajir
- Type: server-rendered HTML, Playwright required
- Jobs grouped by department sections

## DOM structure

Jobs organized under department headings (e.g. Admin, Finance)

Per job posting:
- Container: `.ashby-job-posting-brief-list a` anchor
- Link: anchor's `href`
- Title: `.ashby-job-posting-brief-title` inner text
- Details line: `.ashby-job-posting-brief-details p` inner text (format: "Department • Location • JobType • Workplace")

## Details line parsing

The details paragraph contains pipe-separated fields:
```
"Admin • Lahore • Full time • On-site"
```

Split by " • " to extract:
1. Department
2. Location
3. Job type
4. Workplace (additional field, not stored)

## Known fields per job

- title
- link (relative href joined with sourceUrl)
- location (from details line, second field)
- department (from details line, first field)
- jobType (from details line, third field)
- postedAt — not available, left as empty string
- state — always "open"

## Pagination

None visible in the sample. Single page loads all jobs. If pagination exists, it's not yet triggered.

## Sanity guard

Same as other scrapers — zero-job drop keeps old snapshot.

## Open questions

- Confirm whether the page loads all jobs on initial page load or if there's lazy-loading / pagination that needs to be triggered
