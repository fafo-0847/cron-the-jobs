## Systems Source Notes

- Source URL: https://career55.sapsf.eu/career?company=systemvent&career_ns=job_listing_summary&navBarLevel=JOB_SEARCH
- ATS type: SAP SuccessFactors
- Fetch method: Playwright browser automation, because the job rows are rendered after page load
- Pagination: click `Next Page` until no next button remains
- Pattern: each opening is rendered as a `tr.jobResultItem` row
- Title: `a.jobTitle`
- Req id: the `ID:` value inside the note section
- Posted date: the `Posted on` value inside the note section
- Country and city: values in the `onclick` payload for the `jobMFieldContent` spans
- Experience: the trailing `jobContentEM` value in the note section
- Job id: `md5(title + link)`

## Example Job Row

- Title: Consultant Development
- Req Id: 5178
- Country: Pakistan
- City: Faisalabad, Islamabad, Karachi, Lahore, Multan
- Experience: 5-8 Years

## Expected State Shape

```json
{
  "sourceUrl": "https://career55.sapsf.eu/career?company=systemvent&career_ns=job_listing_summary&navBarLevel=JOB_SEARCH",
  "fetchedAt": "2026-06-13T00:00:00Z",
  "state": "open",
  "jobs": [
    {
      "id": "md5_of_title_plus_link",
      "reqId": "5178",
      "title": "Consultant Development",
      "link": "https://career55.sapsf.eu/career?...",
      "postedAt": "10/20/2025",
      "country": "Pakistan",
      "city": "Faisalabad, Islamabad, Karachi, Lahore, Multan",
      "experience": "5-8 Years"
    }
  ]
}
```