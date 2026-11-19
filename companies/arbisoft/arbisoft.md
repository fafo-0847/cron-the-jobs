## Arbisoft Source Notes

- Source URL: https://arbisoft.hirestream.io/api/v1/jobs/published-jobs/?timezone=Asia%2FKarachi&offset=0&limit=20&order=featured
- Pattern: API response containing paginated job data.
- Pagination: Driven by the `next` URL in the response payload.
- Job Identifier: `uuid`
- Title: `title`
- Department: `department`
- Location: `location`
- Date: `modified`
- Link constructed via: `https://arbisoft.hirestream.io/jobs/{uuid}`

## Example Job Card

- Title: Senior Data Engineer
- Location: Arbisoft, Lahore, Islamabad, Karachi
- Department: Software Engineering
- Posted At: 2026-06-12T13:00:34.150214Z
- Link: https://arbisoft.hirestream.io/jobs/efe94df5-534d-4942-ac7a-15c34f7ac640

## Expected State Shape

```json
{
  "sourceUrl": "https://arbisoft.hirestream.io/api/v1/jobs/published-jobs/?timezone=Asia%2FKarachi&offset=0&limit=20&order=featured",
  "fetchedAt": "2026-06-13T...",
  "state": "open",
  "jobs": [
    {
      "id": "md5(title+link)",
      "title": "Senior Data Engineer",
      "link": "https://arbisoft.hirestream.io/jobs/efe94df5-534d-4942-ac7a-15c34f7ac640",
      "location": "Arbisoft, Lahore, Islamabad, Karachi",
      "department": "Software Engineering",
      "postedAt": "2026-06-12T13:00:34.150214Z",
      "state": "open"
    }
  ]
}
```