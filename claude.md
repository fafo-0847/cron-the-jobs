# Claude Guide

Use this file as the working context for future company scrape tasks.

## Reusable Scrape Pattern

- Prefer async modular functions.
- Avoid classes unless a scraper truly needs stateful behavior.
- Keep helper functions small and single-purpose.
- Use named intermediary variables.
- Keep control flow explicit.
- use try-except blocks to handle errors gracefully.
- use logging where required.

## Pattern That Worked

- Fetch the openings page directly.
- Parse repeated card blocks from the HTML response.
- Extract the title, link, type, location, posted time, and category.
- Generate job ids with `md5(title + link)`.
- Return a single company JSON snapshot with `sourceUrl`, `fetchedAt`, `state`, and `jobs`.
- Store that snapshot in a company-local JSON file and overwrite it on each scrape.

## Company-Specific Notes

- Keep scraper-specific extraction patterns in the company folder notes, not in this global guide.
- Use the company `*.md` file and the company `*.json` snapshot file for source-specific details.

## Preferred File Layout For Company Scrapers

- `companies/<company>/<company>.py` for the scraper module.
- `companies/<company>/<company>.json` for the latest snapshot.
- `companies/<company>/<company>.md` for source notes and extraction hints.

## Recommended Flow

1. Read the company notes first.
2. Inspect the current scraper file.
3. Decide whether the page needs direct HTTP or browser automation.
4. Build a fetch function.
5. Build a parser for the repeating job card shape.
6. Build a state writer for the JSON snapshot.
7. Run a syntax check.
8. Run a small parser smoke test.
9. Run the scraper once and confirm the JSON file updates.
10. Refine <company>.md file.


## Validation Habits

- Use `python -m py_compile` before a live run.
- Use a sample HTML block to verify the parser before hitting the live page.
- If a native dependency causes problems, fall back to a stdlib-compatible path when possible.
- Use `python -m package.module` when running modules.

