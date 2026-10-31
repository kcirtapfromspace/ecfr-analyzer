# Frontend evaluation: the slice every candidate implements

Goal: compare htmx, raw JS, SvelteKit and Observable Framework on **ease of use, readability, testability and bloat** by building the same small slice of the eCFR UI. Not a full port.

## Data (read-only; identical for all)
`fixtures/api/agencies.json` (316 agencies), `fixtures/api/agencies/{slug}.json` (detail), `fixtures/api/agencies/{slug}/history.json` (`{"slug", "years": [{"year", "substantive", "nonsubstantive", "removed"}]}`). Field meanings are in `../CONTRACT.md`. Use no other files.

## Pages and behavior
1. **Index**
   - **Table** `table[data-testid=agencies]` with columns Agency, Words, Restrictions / 1k, Unchanged since 2017, Flagged parts. The header cells are `th[data-sort=name|words|density|stale_share|flagged_parts]`. Each body row is `tr[data-slug=<slug>]`. With no search, only top-level agencies (`parent_slug == null`, 153) are visible.
   - **Sort** by clicking a header. A numeric column sorts descending on the first click; Agency sorts ascending (case-insensitive) on the first click. Clicking the same header again reverses the order. Nulls rank lowest. The active header carries `aria-sort="ascending|descending"` and shows ▲/▼.
   - **Search** with `input[data-testid=search]`: a case-insensitive substring match on `name + " " + short_name` across **all** 316 agencies (sub-agencies included). An empty search shows the top-level agencies only.
   - **Scatter** `[data-testid=scatter]`: top-level agencies with words ≥ 1,000; x = words (log scale), y = density. Clicking a point opens that agency's detail (nice to have; not tested).
   - Number formats: words en-US with thousands separators; density and percentages with 1 decimal; null shows "—".
2. **Detail** for one agency, reached by clicking its row. It may be a new page or a panel on the same page.
   - `[data-testid=detail-name]` holds the agency name.
   - `[data-testid=detail-words]` holds the words, e.g. `18,133,322`.
   - `[data-testid=detail-density]` holds the density with 1 decimal, e.g. `10.3`.
   - `[data-testid=history]` is a stacked bar chart of `years` (substantive, nonsubstantive, removed).

## Constraints
- **Output** is static files only. They must work when served under the subpath `/ecfr-analyzer/` (as GitHub Pages serves a project site) by a plain static server that supports HTTP Range requests.
- **Charts** use Chart.js 4.4.1 for htmx, raw JS and SvelteKit. Observable Framework uses its built-in Observable Plot, which is the idiomatic choice there; it's a different library, measured separately.
- **Testability:** the sort and filter logic is pure and unit-testable without a browser (e.g. `sortRows(rows, key, dir)`, `filterRows(rows, query)`). Each candidate has at least these unit tests:
  - density descending puts "Architectural and Transportation Barriers Compliance Board" first
  - nulls go last when descending
  - name ascending puts "Administrative Committee of the Federal Register" first
  - "occupational" matches exactly 2 agencies, one of them a sub-agency
  - an empty query yields the 153 top-level agencies
- **Shared e2e:** `e2e/slice.spec.js` (Playwright) runs unchanged against every candidate.
- Keep code readable and idiomatic for the framework. Don't optimize for line count.
