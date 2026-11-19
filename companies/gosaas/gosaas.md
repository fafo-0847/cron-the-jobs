## GoSaaS Source Notes

- Source URL: https://www.gosaas.ai/careers#jobs-lists
- Pattern: jobs are rendered inside `div.listing__item div.content-card`. Job listings are loaded dynamically based on location filters.
- Location filter: `a[filter-category-eq='Pakistan']` is clicked to filter jobs by location.
- Card URL: `a.content-card__link` (`href` attribute)
- Title: `h4.content-card__title-tag`
- Location: `div.content-card__label`
- Filtering: Only jobs with `location == "Pakistan"` are saved as requested.

## Example Job Card

- Title: DevOps Engineer
- Location: Pakistan
- Posted At: "" (not provided in HTML)
- Link: https://gosaas.bamboohr.com/careers/237

## Expected State Shape

```json
{
  "sourceUrl": "https://www.gosaas.ai/careers",
  "fetchedAt": "2026-06-13T...",
  "state": "open",
  "jobs": [
    {
      "id": "md5(title+link)",
      "title": "DevOps Engineer",
      "link": "https://gosaas.bamboohr.com/careers/237",
      "location": "Pakistan",
      "postedAt": "",
      "state": "open"
    }
  ]
}
```
