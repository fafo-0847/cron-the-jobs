## CureMD Source Notes

- Source URL: https://curemd.wd1.myworkdayjobs.com/en-US/CureMD
- Pattern: standard Workday jobs page. Jobs are in `li.css-1q2dra3` or `ul[role="list"] > li`.
- Pagination: Workday next button `button[aria-label="next"]` or `button[aria-label="Next"]`. Disabled when last page is reached.
- Card URL: `a[data-automation-id="jobTitle"]` (`href` attribute)
- Title: text of `a[data-automation-id="jobTitle"]`
- Location: `div[data-automation-id="locations"] dd`
- Date: `div[data-automation-id="postedOn"] dd`
- Job Code: `ul[data-automation-id="subtitle"] li`

## Example Job Card

- Title: International Recruiter
- Location: Lahore
- Posted At: Posted 30+ Days Ago
- Job Code: JR102161
- Link: https://curemd.wd1.myworkdayjobs.com/en-US/CureMD/job/Lahore/International-Recruiter_JR102161

## Expected State Shape

```json
{
  "sourceUrl": "https://curemd.wd1.myworkdayjobs.com/en-US/CureMD",
  "fetchedAt": "2026-06-13T...",
  "state": "open",
  "jobs": [
    {
      "id": "md5(title+link)",
      "title": "International Recruiter",
      "link": "https://curemd.wd1.myworkdayjobs.com/en-US/CureMD/job/Lahore/International-Recruiter_JR102161",
      "location": "Lahore",
      "postedAt": "Posted 30+ Days Ago",
      "jobCode": "JR102161",
      "state": "open"
    }
  ]
}
```
