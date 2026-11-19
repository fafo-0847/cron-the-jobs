# Soliton — Career Page Notes

## Source

- Platform: Custom API (JSON)
- API: https://www.solitontechnologies.com/backend/public/api/getJobs
- Type: direct JSON API — no Playwright needed
- Career page (reference only): https://www.solitontechnologies.com/careers/

## Response shape

Simple flat array under `jobs` key:

```json
{
  "status": "success",
  "jobs": [
    {
      "job_title": "...",
      "job_location": "...",
      "id": 134,
      "job_type": 1
    }
  ]
}
```

## Job link construction

Career page URLs are built from the job `id`:
```
https://www.solitontechnologies.com/careers/{id}
```

## Known fields per job

- title (from `job_title`)
- link (constructed from `id`)
- location (from `job_location`)
- jobType (from `job_type`, stored as string)
- department — not available, left as empty string
- postedAt — not available, left as empty string
- state — always "open"

## Pagination

None. Single API response returns all jobs.

## Sanity guard

Same as other scrapers — zero-job drop keeps old snapshot.

## Open questions

- Verify that the career page URL pattern `/careers/{id}` is correct and leads to the actual job posting page
- Confirm what `job_type` values mean (e.g. does 1 mean Full-time, 2 mean Contract, etc.)
