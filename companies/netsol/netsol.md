## Netsol Source Notes

- Source URL: https://careers.netsoltech.com/openings/
- Pattern: each opening is rendered as an `article.loadmore-item` card
- Card URL: `data-url` on the article element
- Title: `h2.loop-item-title a`
- Type: `span.job-type a`
- Location: `span.job-location a`
- Date range: `time.entry-date`
- Category: `span.job-category a`
- Action link: `a.btn.btn-primary` with text `View Job`

## Example Job Card

- Title: Head of Web Development
- Type: Permanent
- Location: Lahore
- Category: Software & Web Development
- Posted At: 2026-06-01T04:31:38+00:00
- Card URL: https://careers.netsoltech.com/openings/head-of-web-development/

## Expected State Shape

```json
{
  "sourceUrl": "https://careers.netsoltech.com/openings/",
  "state": "open",
  "jobs": [
    {
      "title": "Head of Web Development",
      "link": "https://careers.netsoltech.com/openings/head-of-web-development/",
      "type": "Permanent",
      "location": "Lahore",
      "category": "Software & Web Development",
      "postedAt": "2026-06-01T04:31:38+00:00"
    }
  ]
}
```