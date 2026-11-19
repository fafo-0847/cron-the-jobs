# 10Pearls — Career Page Notes

## Source

- Platform: Resumator (Hiring platform with public JSON API)
- API: https://api.resumatorapi.com/v1/jobs?apikey=jB0b57gnKdU9rqBWvqQpxzITAPrHUFaz
- Type: direct JSON API — no Playwright needed, flat response array
- Career page (reference only): https://10pearls.resumatorsite.com/

## Response shape

Simple flat array of job objects, one per posting. Each job has:
- `id` — Resumator job ID
- `title` — job title
- `board_code` — used to build the apply link
- `country_id`, `city` — location (joined with ", ")
- `department` — department name (often empty string on Resumator)
- `type` — job type (e.g. "Contracted", "Full-time")
- `original_open_date` — YYYY-MM-DD string, stored as-is in `postedAt`
- `status` — always "Open" for active postings (not filtered by scraper, Resumator only returns open jobs)

## Apply link construction

Resumator doesn't expose direct application links in the JSON. Link is built from pattern:
```
https://10pearls.resumatorsite.com/apply/{board_code}/{job_id}
```

If `board_code` is missing or empty, the job is skipped (no way to apply).

## Known fields per job

- title
- link
- location (city + country)
- department
- jobType
- postedAt (original_open_date as-is, no conversion to ISO)
- state — always "open"

## Pagination

None. Single API response returns all open jobs.

## Sanity guard

Same as other scrapers — zero-job drop triggers a warning and keeps old snapshot.

## Open questions

- Confirm the apply link pattern works once live (assumed from Resumator's standard URL structure, not confirmed with actual click-through)
- `department` is often empty on Resumator boards — worth checking if the API ever populates it or if it's always blank
