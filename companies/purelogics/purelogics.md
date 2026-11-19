## PureLogics Source Notes

- Source URL: https://purelogics.com/careers/
- Pattern: each opening is rendered as an `li.job_listing` item
- Card URL: `a` element inside `li` (`href` attribute)
- Title: `div.position h3`
- Location: `div.location`
- Date: `ul.meta li.date time` (`datetime` attribute)
- Load more button: `a.load_more_jobs` (standard WP Job Manager)

## Example Job Card

- Title: Business Development Intern (FAST Sales)
- Location: Lahore, Pakistan
- Posted At: 2026-06-09
- Link: https://purelogics.com/job/business-development-intern-fast-sales/

## Expected State Shape

```json
{
  "sourceUrl": "https://purelogics.com/careers/",
  "fetchedAt": "2026-06-13T...",
  "state": "open",
  "jobs": [
    {
      "id": "md5(title+link)",
      "title": "Business Development Intern (FAST Sales)",
      "link": "https://purelogics.com/job/business-development-intern-fast-sales/",
      "location": "Lahore, Pakistan",
      "postedAt": "2026-06-09",
      "state": "open"
    }
  ]
}
```