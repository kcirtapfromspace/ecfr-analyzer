# eCFR Analyzer — agreed build plan (Claude + Codex)

Process: Claude and Codex each wrote a plan independently (from the same verified API facts in `facts.md`). Each then critiqued the other's plan. Codex signed off on the one item left open. Tiebreak rule: **fewer lines and easier to walk through on a screen-share**, under the ≤1,200 LOC / ~4 h budget.

## Agreed recommendations

**Stack**
1. Python 3.12 + FastAPI + uvicorn. Routes return plain dicts. The free `/docs` page shows reviewers the "APIs that retrieve stored data" with no extra code.
2. SQLite via stdlib `sqlite3`, no ORM. One static `index.html` + vanilla JS. Chart.js vendored under `vendor/`; the doc states that this third-party file is excluded from the LOC count. No build step.

**Ingest** (`python ingest.py`, manual CLI)
3. Refuse to run if `titles.json` says `import_in_progress`. Pin `meta.date` for every download. Skip reserved titles.
4. Download each title's full XML with compression on (without it the API returns HTTP 406). Cache raw files under `data/raw/{meta.date}/`; a cached file means "skip" only within that snapshot, so ingest can resume without reusing stale XML. Use timeouts, retries, and 2–4 workers. **Measure total time on the first run; don't trust an estimate.**
5. History: page through `versions/title-N.json` (1,000 rows/page). Assert that the fetched rows equal `meta.result_count`.
6. Parse with `ElementTree.iterparse`. On each PART (DIV5) end event, collect its text first, then `clear()`. Clearing before collecting destroys the text you are measuring.
7. Build into `ecfr.new.sqlite` and validate it: all titles present, history totals match, part numbers unique nationwide, words outside any part counted, and **every agency matches ≥1 part** (print any that match none; otherwise a format mismatch silently reports 0 words). Copy the old checksums in as `prev_checksum`, close the DB, then `os.replace()` it over `ecfr.sqlite`. A failed refresh leaves the old data in place.

**Agency attribution**
8. The unit is the **PART**, keyed by `(title, part)`. Record its subtitle/chapter/subchapter ancestors, with identifiers kept as strings (chapter `"0"` exists).
9. A reference matches a part when **every field it specifies** matches. That one rule covers all 5 reference shapes.
10. `agency_part(slug, title, part)` stores membership. A parent's rows include all of its children's parts, unique. Roll-ups are `SUM` over distinct parts; **never sum child totals**. The UI says that agencies can overlap, so their totals are not additive.
11. Show coverage: "text within parts" scope, words outside any part, and history events with no matching part.

**Metrics**
12. **Word count**: count of `[^\W_]+` runs in the text inside the agency's parts (headings, tables, and appendices included).
13. **History**: version rows dated **on/after 2017-01-01**, de-duplicated on `(title, type, identifier, date)`. This includes new sections *and* amendments, split into substantive and non-substantive. Removals are a separate series and are not double-counted. Show yearly bars labelled *"Recorded section changes since 2017 (eCFR versioner)"* and the "current ownership" basis. Rows before the cutoff are shown as a count of **baseline version rows**. Methodology note: *2017-01-01 is an empirical reporting cutoff, not a verified start of historical availability.* Ingest prints, for each title, the share of rows before the cutoff and the latest pre-cutoff date.
14. **Checksum**: per part, SHA-256 of NFC-normalized, whitespace-collapsed text (case and punctuation kept). Per agency, SHA-256 over `title|part|part_hash` lines in numeric-title, document order. Identifiers are hashed too, so moving text between parts changes the checksum. The UI shows a "changed since last ingest" badge.
15. **Custom metric: restriction density.** Per 1,000 words, count the word-bounded, case-insensitive terms *shall, must, may not, required, prohibited* (the RegData/Mercatus list). Present it as a **lexical signal for prioritizing review**, not a measure of actual burden.

**Storage**: `agency(slug, name, short_name, parent_slug, refs_json)`, `part(title, part, subtitle, chapter, subchapter, heading, ord, words, restrictions, sha256)`, `agency_part(slug, title, part)`, `version(title, part, type, identifier, date, amendment_date, substantive, removed)`, `agency_metric(slug, words, restrictions, checksum, prev_checksum, last_amended)`, `meta(key, value)`.

**API**
16. `GET /api/meta` (snapshot date, totals, coverage, baseline count) · `GET /api/agencies` (list with metrics) · `GET /api/agencies/{slug}` (summary, references, children, top parts) · `GET /api/agencies/{slug}/history` (yearly series + unmatched count).

**UI**
17. One page. It has summary cards, a top-N horizontal bar chart, and a searchable, sortable agency table with expandable children. A detail panel shows words, density, a copyable checksum with the changed badge, the yearly history bars, references, and caveats.

**Budget**
18. LOC: ingest/parser 300 · attribution/metrics 150 · DB + API 150 · HTML/JS/CSS 350 · CLI/config 50 · reserve 150 = **1,150**. Time: ingest 90 min · backend 40 · UI 60 · tests/doc 50. Hosting is optional and comes last: a Dockerfile and a free host, only after correctness, screenshots, and the doc are done.

**Tests** (few, high value)
19. A fixture XML covering all 5 reference shapes, chapter `"0"`, overlapping references, and the parent/child union. A check that text is counted once and that iterparse clearing loses nothing. A check that the checksum ignores whitespace but catches punctuation and identifier changes. Checks for the history cutoff, de-duplication, removals, unmatched events, and pagination totals.

**Submission doc**
20. Skills fit · **measured** duration (start the clock at the first commit) · run/refresh commands · metric definitions + limitations · screenshots · hosted link if any.
21. AI use, told honestly: Claude and Codex planned independently and critiqued each other's plans. API behavior was verified by direct requests, not assumed. Say which code was generated and how it was checked. The author must be able to explain every line.

**How Claude and Codex would build it**
22. Contracts first: freeze the schema and API shapes before writing code. One agent implements a component, and the other reviews it against `facts.md` and the tests. The user approves any change from this plan. If ingest time or LOC goes over budget, stop and re-plan instead of pushing on.

## Where we disagreed and how it was resolved

| Topic | Claude R1 | Codex R1 | Agreed | Deciding reason |
|---|---|---|---|---|
| Framework | FastAPI + static page | Flask + Jinja | FastAPI | Free `/docs`; no templates needed |
| Storage unit | PART | Every DIV node's own text | PART + report excluded words | Verified: parts are unique and contain all sections; fewer LOC |
| Parser | iterparse | SAX | iterparse | Measured 3.2 s on 157 MB; easier to show |
| Refresh | Single DB + prev checksum | Multi-snapshot tables | Build new DB, validate, swap | Gives Codex's safety with Claude's size |
| Word | Whitespace tokens | `[^\W_]+` runs | Codex's | Doesn't count "§" or "—" |
| Checksum | Sorted bare part hashes | Canonical records | `title\|part\|hash` in doc order | Codex: bare hashes miss moved text |
| History baseline | Not handled | Count initial versions | Cutoff at 2017-01-01 | 62% of Title 1 rows are a 2015 baseline. Claude's "drop first versions" was wrong: it drops 82/320 real additions (both agents caught it) |
| History grain | Yearly | Monthly | Yearly | Readable across ~150 agencies |
| Restriction terms | + "may not" | 4 single words | + "may not", lexical caveat | Matches the published RegData list |
| Hosting | Optional | Avoid | Optional, last | It's an "if applicable" submission item |
| Pagination | Missed | Missed | Paginate + assert totals | Found by probing between rounds |

## Verify first when the build starts
- Part uniqueness and containment across **all** titles (only Titles 1 and 40 have been checked).
- Subtitle (DIV2) `N` values use the same format as the 15 subtitle references (subchapter format already matches: `A`, `B`, …).
- Total ingest time and history page count nationwide.
- The cutoff diagnostics per title (does any title's baseline fall after 2017-01-01?).
