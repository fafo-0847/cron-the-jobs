# CarbonTeq — Career Page Notes

## Source

- Platform: Resumator API (hosted ATS)
- API URL: https://api.resumatorapi.com/v1/jobs/status/open?apikey=Y5uJhnJlBk1AdkHa5e0G1tie1v0ARW8d
- Type: JSON API, no Playwright needed
- Returns array of open job objects

## API Response Schema

Each job object in the response array contains:
- `id` — job API ID (e.g. `job_20260201171654_V6CMNQQXP6O5F66O`)
- `title` — job title
- `country_id` — country name
- `city` — city name
- `state` — state/province name
- `department` — department name
- `type` — employment type (e.g. "Temporary", "Full-time", "Contract")
- `original_open_date` — posted date (YYYY-MM-DD format)
- Other metadata: zip, notes, board_code, etc. (not used)

## Location Construction

Location is built from city, state, country in order, joined with ", ":
```
"Lahore, Punjab, Pakistan"
```

## Link Construction

Job links are built from `board_code` and job API `id`:
```
https://carbonteq.resumatorsite.com/apply/{board_code}/{jobApiId}
```

Board code: `ImhgOLzP8U` (hardcoded; check if it changes per company)

## Known Fields per Job

- title
- link (constructed from board_code + job API id)
- location (city, state, country joined)
- department
- jobType (from `type` field)
- postedAt (from `original_open_date`, ISO date string)
- state — always "open" (filtered by API endpoint)

## No Pagination

API endpoint already filters to status=open. Returns all open jobs in one response.

## Sanity Guard

Same as other scrapers — zero-job drop keeps old snapshot.

## Open Questions

- Verify board_code is consistent across runs or if it should be extracted per company
- Confirm link pattern works and leads to application page
