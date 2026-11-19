## Careem Source Notes

- Source URL: https://boards-api.greenhouse.io/v1/boards/careem/departments
- Pattern: API response containing a list of `departments`, each having an array of `jobs`.
- Pagination: None. The endpoint returns all active jobs nested inside departments.
- Title: `job.title`
- Department: `department.name`
- Location: `job.location.name`
- Date: `job.updated_at`
- Link: `job.absolute_url`

## Example Job Card

- Title: CRM & Martech Specialist
- Location: Karachi, Pakistan
- Department: EA Operations
- Posted At: 2026-06-10T11:09:19-04:00
- Link: https://boards.greenhouse.io/careem/jobs/8553672002?gh_jid=8553672002

## Expected State Shape

```json
{
  "sourceUrl": "https://boards-api.greenhouse.io/v1/boards/careem/departments",
  "fetchedAt": "2026-06-20T...",
  "state": "open",
  "jobs": [
    {
      "id": "09d0c05c8500407d57cbe33e139c12dc",
      "title": "CRM & Martech Specialist",
      "link": "https://boards.greenhouse.io/careem/jobs/8553672002?gh_jid=8553672002",
      "location": "Karachi, Pakistan",
      "department": "EA Operations",
      "postedAt": "2026-06-10T11:09:19-04:00",
      "state": "open"
    }
  ]
}
```