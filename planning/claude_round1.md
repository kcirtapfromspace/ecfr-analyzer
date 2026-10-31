# Claude round-1 plan (written independently of Codex)

1. **Stack**
   - Python 3.12 + FastAPI + uvicorn: few lines per route, and `/docs` (OpenAPI) shows the APIs for free.
   - SQLite via stdlib `sqlite3`, no ORM: one file, easy to ship and to inspect live in the interview.
   - Frontend: one static `index.html` + `app.js`, vanilla JS + Chart.js from a CDN. No build step, no framework.
   - `httpx` for downloads, `lxml.etree.iterparse` (or stdlib ElementTree) for streaming parse.

2. **Ingest** (`python ingest.py`, offline, idempotent)
   - Fetch agencies.json and titles.json; skip reserved titles; record `meta.date` as the snapshot date.
   - For each title: download `full/{date}/title-N.xml` with gzip (this avoids the 406), save it compressed to `data/raw/`, then stream-parse it with `iterparse` + `elem.clear()`. Use 4 parallel downloads. Expect ~5–10 minutes total.
   - For each title: download `versions/title-N.json` for history.
   - Refresh: re-run the script. The previous checksum per agency is kept so the UI can flag "changed since last ingest".

3. **Agency attribution**
   - The unit of storage is the PART (DIV5). For each part, record its ancestors (subtitle, chapter, subchapter). Part numbers are unique within a title, so `(title, part)` is the key.
   - A ref matches a part when every field the ref specifies matches. This handles all 5 ref shapes without special cases.
   - An agency's part set = union of the parts matched by its own refs. A parent's rolled-up set = its own refs + all child refs, de-duplicated by `(title, part)` before summing. Never sum the child totals.
   - Report the coverage: the share of all words that are attributed to at least one agency.

4. **Metrics**
   - (a) **Word count**: whitespace-delimited tokens of all text inside the agency's parts (tags stripped). Show own and rolled-up values.
   - (b) **History**: section-version rows from the versions endpoint, joined to agencies by `(title, part)`. Show changes per year, split substantive vs. non-substantive, plus the last amended date. No word-count-over-time; it would need full-text snapshots per date.
   - (c) **Checksum**: per part, SHA-256 of whitespace-normalized text. Per agency, SHA-256 of its sorted part hashes (Merkle-style). It is deterministic, cheap to compute, and lets you find the exact part that changed.
   - (d) **Custom: restriction density.** Count "shall", "must", "may not", "required", "prohibited" (the RegData method) per 1,000 words. Rationale: word count measures volume, restrictions measure binding obligations. High density × high volume points to the most burdensome rule sets.

5. **Schema**: `snapshot(ecfr_date, ingested_at)`, `agency(slug PK, name, short_name, parent_slug)`, `agency_ref(slug, title, subtitle, chapter, subchapter, part)`, `part(title, part, subtitle, chapter, subchapter, heading, words, restrictions, sha256)`, `version(title, part, section, date, substantive, removed)`, `agency_metric(slug, words, restrictions, checksum, prev_checksum, last_amended)`.

6. **API**
   - `GET /api/meta` → snapshot date, totals, coverage
   - `GET /api/agencies` → list with metrics
   - `GET /api/agencies/{slug}` → detail + top parts
   - `GET /api/agencies/{slug}/history` → `[{year, changes, substantive}]`

7. **UI**: one page. It has summary cards, a top-15 bar chart, and a sortable, searchable agency table (words, density, short checksum, changed flag, changes in the last 5 years). Clicking a row opens a detail panel with the history chart and the top parts. A toggle switches between own and rolled-up values.

8. **LOC**: ingest 300, db/metrics 150, api 150, html+js 400, css 80 = 1,080.

9. **Tests**: attribution on a tiny fixture XML (subchapter ref, parent/child overlap); checksum determinism; counting; API smoke test against a fixture DB.

10. **Risks**
    - Wrong attribution → fixture tests + the coverage number.
    - 157 MB titles → streaming parse + raw cache.
    - Scope creep past 1,200 LOC / 4 h → no build step, no ORM, no auth; drop hosting first.

11. **Submission doc**: run steps, metric definitions + caveats, screenshots, duration (tracked from the first commit), optional hosted link. AI: Claude and Codex co-designed the plan, the author made the calls and verified the API by hand, and the author can explain every line.
