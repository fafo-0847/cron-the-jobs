## Dubizzle Source Notes

- Source URL: https://jobs.dubizzlelabs.com
- Pattern: jobs are rendered inside `ul.positions.location li.position`
- Card URL: `a` element inside `li.position-details` (`href` attribute)
- Title: `h2` inside the `a` element
- Location: `li.location span`
- Department: `li.department span` (optional)

## Example Job Card

- Title: Android Developer
- Location: Lahore, PK
- Department: Mobile Apps
- Posted At: "" (not provided in HTML)
- Link: https://jobs.dubizzlelabs.com/p/3466afff651801-android-developer

## Expected State Shape

```json
{
  "sourceUrl": "https://jobs.dubizzlelabs.com",
  "fetchedAt": "2026-06-13T...",
  "state": "open",
  "jobs": [
    {
      "id": "md5(title+link)",
      "title": "Android Developer",
      "link": "https://jobs.dubizzlelabs.com/p/3466afff651801-android-developer",
      "location": "Lahore, PK",
      "department": "Mobile Apps",
      "postedAt": "",
      "state": "open"
    }
  ]
}
```
