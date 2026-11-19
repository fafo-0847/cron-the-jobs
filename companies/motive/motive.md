## Motive Source Notes

- Source URL: https://boards-api.greenhouse.io/v1/boards/gomotive/departments
- Pattern: API response containing a list of `departments`, each having an array of `jobs`.
- Pagination: None. The endpoint returns all active jobs nested inside departments.
- Title: `job.title`
- Department: `department.name`
- Location: `job.location.name`
- Date: `job.updated_at`
- Link: `job.absolute_url`

## Example Job Card

- Title: Director, Technical & Operational Revenue
- Location: Hybrid - San Francisco, California
- Department: Accounting
- Posted At: 2026-05-28T08:28:27-04:00
- Link: https://job-boards.greenhouse.io/gomotive/jobs/8505093002

## Expected State Shape

```json
{
  "sourceUrl": "https://boards-api.greenhouse.io/v1/boards/gomotive/departments",
  "fetchedAt": "2026-06-13T...",
  "state": "open",
  "jobs": [
    {
      "id": "md5(title+link)",
      "title": "Director, Technical & Operational Revenue",
      "link": "https://job-boards.greenhouse.io/gomotive/jobs/8505093002",
      "location": "Hybrid - San Francisco, California",
      "department": "Accounting",
      "postedAt": "2026-05-28T08:28:27-04:00",
      "state": "open"
    }
  ]
}
```