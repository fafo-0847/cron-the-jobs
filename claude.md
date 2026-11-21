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


## Failure Reporting (added Nov 2026)

- Scrapers catch their own errors and keep the old snapshot on a zero-job scrape, so `main.py`
  does not rely on exceptions alone. `health.py` collects every WARNING+/ERROR log line emitted
  while a company runs and writes an entry to `output/errors_<date>.json` (and the email) when:
  - `exception`: the scraper raised,
  - `zero_jobs`: it had jobs before and returned 0 now,
  - `error_no_jobs`: it returned 0 jobs and logged an ERROR,
  - `partial_error`: it returned jobs but also logged an ERROR.
- Each entry has `company`, `type`, `reason` (classified: Cloudflare, DNS, 401/403/404/5xx, non-JSON, timeout, ...),
  `error`, `details`, `oldJobCount`, `newJobCount`.
- `python failure_report.py [N]` summarises the last N runs (default 30): failures per company and reasons.
- So that errors are reported, log failures with `logger.exception` / `logger.error`, not `warning`.

## Empty Boards

- When a source answers correctly and really lists no openings, return `"confirmedEmpty": True`
  in the `fetchState` state. `main.py` then clears the snapshot instead of keeping stale jobs, and
  does not report an error. Only set it on positive evidence (ATS API returned an empty list, or
  the page shows its "no open positions" notice) — never on a timeout.
- Playwright pages: use `companies/_shared/emptyboard.waitForJobsOrEmptyNotice(page, jobSelector, noticePattern)`.

## Shared Helpers (`companies/_shared/`, skipped by main.py)

- `rippling.py` (ats.rippling.com, reads `__NEXT_DATA__`), `joincom.py` (join.com), `peopleforce.py`,
  `jazzhr.py` (*.applytojob.com), `bamboohr.py` (*.bamboohr.com/careers/list), `nextjs.py`
  (read job JSON out of Next.js App Router flight data), `browser.py` (desktop UA, retries,
  readable 4xx/5xx/Cloudflare errors), `emptyboard.py`.
- Prefer an ATS JSON endpoint or server-rendered HTML over Playwright selectors: CSS-in-JS / Tailwind
  class names change on every redesign. Keep job ids stable (`md5(title + stableId)`) when switching
  sources so existing jobs are not re-reported as new.
- `main.py` uses the module's `snapshotPath` to decide first-run; keep `snapshotPath` defined.

## Tests

- `python -m pytest -q tests` (offline parser tests with markup captured from live pages; the
  `emptyboard` test uses headless Chromium and skips if it is not installed).
