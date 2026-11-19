# TCP Software — Career Page Notes

## Source

- Platform: Custom WJB (Workable Job Board widget) HTML
- URL: https://tcpsoftware.com/careers/
- Type: server-rendered HTML, Playwright required

## DOM structure

Jobs grouped under department headings (h2.wjb-dept-title)

Per job item (.wjb-job-item):
- Data attributes: `data-shortcode`, `data-country`, `data-city`, `data-remote` (0 or 1), `data-department`
- Title: `.wjb-job-title` inner text
- Location: `.wjb-job-location` inner text

## Link construction

Job links are built from the shortcode (no actual href in HTML):
```
https://tcpsoftware.com/careers/?job={shortcode}
```

## Job type inference

- `data-remote="1"` → "Remote"
- `data-remote="0"` → "On-site"

## Known fields per job

- title (from .wjb-job-title)
- link (constructed from shortcode)
- location (from .wjb-job-location)
- department (from data-department attribute)
- jobType (inferred from data-remote: Remote or On-site)
- postedAt — not available, left as empty string
- state — always "open"

## Pagination

None visible in the sample. Single page loads all jobs grouped by department. If pagination exists, it's not yet triggered.

## Sanity guard

Same as other scrapers — zero-job drop keeps old snapshot.

## Open questions

- Confirm whether the page loads all jobs on initial page load or if there's lazy-loading / pagination that needs to be triggered
- Verify that the constructed link pattern `?job={shortcode}` actually works and leads to the job posting detail page
