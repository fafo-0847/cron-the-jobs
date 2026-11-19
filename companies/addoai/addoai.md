# AddoAI — Career Page Notes

## Source

- Platform: HireStream (custom careers portal)
- URL: https://addo-ai.hirestream.io/careers/jobs/?offset=0&search=&departments=&pageSize=9
- Type: server-rendered HTML with Material-UI components, Playwright required

## DOM structure

Jobs displayed as Material-UI cards in a grid (`.MuiGrid-container`)

Container: `.MuiGrid-item` — one per job

Per card:
- Title: element with id pattern `home-job-*-card-title`
- Department: element with id pattern `home-job-*-department`
- Location: element with id pattern `home-job-*-location`
- Remote status: element with id pattern `home-job-*-remote-section-heading` (contains "Remote Job" or on-site indicator)

## Link Construction

Job links are constructed from the card's ID:
```
https://addo-ai.hirestream.io/careers/jobs/{cardId}
```

Card ID extracted by removing `-card-title` suffix from the title element's id attribute.

## Job Type Inference

Remote status detected by checking if remote section text contains "Remote":
- Contains "Remote Job" → jobType = "Remote"
- Otherwise → jobType = "On-site"

## Known Fields per Job

- title
- link (constructed from card ID)
- location (from location element)
- department (from department element)
- jobType (inferred from remote status indicator)
- postedAt — not available, left as empty string
- state — always "open"

## Pagination

Page size parameter visible in URL (`pageSize=9`). Single page loads 9 jobs. If pagination exists, it's not yet triggered.

## Sanity Guard

Same as other scrapers — zero-job drop keeps old snapshot.

## Open Questions

- Confirm whether pagination exists (next page button, load more, etc.) and how to handle it
- Verify link pattern works and leads to job detail page
