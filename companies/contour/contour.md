link = https://contour-software.com/jobs/

## Contour Source Notes

- Source URL: https://contour-software.com/jobs/
- API Endpoint: `POST https://contour-software.com/service.php?slug=jobs`
- Pattern: JSON API, not HTML scraping. The page uses JS to fetch from a PHP proxy to Workday.
- Request payload: `{ "appliedFacets": {}, "limit": 50, "offset": 0, "searchText": "" }`
- Response shape: `{ "total": 153, "jobPostings": [...], "facets": [...] }`

## Job Posting Fields

- Title: `jobPostings[].title`
- Location: `jobPostings[].locationsText` (e.g. "PER - Karachi, PK" or "3 Locations")
- Posted: `jobPostings[].postedOn` (e.g. "Posted Yesterday", "Posted 4 Days Ago")
- Job Code: `jobPostings[].bulletFields[0]` (e.g. "R52441")
- Detail Path: `jobPostings[].externalPath` (e.g. "/job/PER---Karachi-PK/Accounting-Trainee_R52441")
- Detail URL: `https://contour-software.com/job-detail/?jobPath=<externalPath>&jobTitle=<title>`

## Filter Facets Available

- `locationMainGroup` → locations (Islamabad, Karachi, Lahore, Remote)
- `timeType` → employment type (Full time, Part time)
- `jobFamilyGroup` → job category (Software Development, Finance, SQA, HR, etc.)
- `workerSubType` → worker type (Regular, Student/Trainee, Temporary)

## Example Job Card

- Title: Accounting Trainee
- Location: PER - Karachi, PK
- Posted: Posted Yesterday
- Job Code: R52441
- Detail Path: /job/PER---Karachi-PK/Accounting-Trainee_R52441

## Expected State Shape

```json
{
  "sourceUrl": "https://contour-software.com/jobs/",
  "fetchedAt": "2026-06-13T...",
  "state": "open",
  "jobs": [
    {
      "id": "md5(title+link)",
      "title": "Accounting Trainee",
      "link": "https://contour-software.com/job-detail/?jobPath=/job/PER---Karachi-PK/Accounting-Trainee_R52441",
      "location": "PER - Karachi, PK",
      "postedAt": "Posted Yesterday",
      "jobCode": "R52441",
      "state": "open"
    }
  ]
}
```