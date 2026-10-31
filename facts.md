# USDS eCFR take-home: assignment + verified API facts

## Assignment (verbatim summary)
- Write code to download the current eCFR data, store it server-side, create APIs that read the stored data, and provide a UI to analyze:
  1. word count per agency
  2. historical changes over time
  3. a checksum for each agency
  - plus at least one custom metric that could help inform decision-making (context: potential deregulation efforts).
- Web-based UI for reviewers.
- Submission: source code (strong preference: <= 1,200 lines of code, excluding tests and auto-generated files), plus a document with: how the author's skills fit, how long it took, link to frontend if applicable, UI screenshots.
- AI use is allowed, but the author must be able to explain how and why AI was used, and walk through the code on a screen-share in a technical interview.
- Designed for ~4 hours excluding setup. "Keep the solution lightweight and focused."

## eCFR API facts (verified by curl on 2026-10-30; do NOT assume behavior beyond these)
- `GET https://www.ecfr.gov/api/admin/v1/agencies.json` -> `{agencies:[...]}`. 153 top-level agencies, 163 child agencies (nested in `children`). Each has name, short_name, display_name, sortable_name, slug, children, cfr_references.
- `cfr_references` (487 total across parents+children) come in 5 shapes:
  - {title, chapter}: 460
  - {title, subtitle}: 14
  - {title, chapter, subchapter}: 8
  - {title, chapter, part}: 4
  - {title, subtitle, chapter}: 1
  - No reference covers a whole title. Every top-level agency has >= 1 ref.
- `GET /api/versioner/v1/titles.json` -> 50 titles with number, name, latest_amended_on, latest_issue_date, up_to_date_as_of, reserved. `meta.date` = current data date (2026-10-29), `meta.import_in_progress`.
- `GET /api/versioner/v1/full/{date}/title-{n}.xml` -> full XML of a title as of a date.
  - Returns HTTP 406 unless the request sends Accept-Encoding allowing compression (curl needs `--compressed`).
  - The `?chapter=III` query param is silently IGNORED (whole title returned).
  - Title 40 (largest): 157 MB uncompressed, 25 MB on the wire, ~10 s. Must stream-parse, not DOM-load.
  - Structure: `<ECFR><DIV1 TYPE="TITLE"> <DIV2 TYPE="SUBTITLE"> <DIV3 TYPE="CHAPTER" N="I"> <DIV4 TYPE="SUBCHAP"> <DIV5 TYPE="PART"> ... <DIV8 TYPE="SECTION">`. Each DIV has N (identifier) and a HEAD. A chapter `N="0"` exists in Title 1.
- `GET /api/versioner/v1/versions/title-{n}.json` -> `{content_versions:[...]}`. One row per section version: date, amendment_date, issue_date, identifier (e.g. "1.1"), name, part, subpart, substantive (bool), removed (bool), type ("section"/"appendix").
  - Rows carry `part` but NOT chapter. The `?chapter=` filter is also silently IGNORED here (same 422 rows with and without it for Title 1).
  - So attributing history to an agency needs a part->chapter mapping (from the structure endpoint or from the XML).
- `GET /api/versioner/v1/structure/{date}/title-{n}.json` -> JSON tree (identifier, label, type, reserved, size, children). Gives the hierarchy without text.
- `GET /api/search/v1/counts/daily?agency_slugs[]={slug}` -> `{dates:{"YYYY-MM-DD": n, ...}}`. Works per agency slug directly (ACUS: 3 dates). Exact semantics of the count are not verified (likely count of matching sections/changes on that date).
- Verified by stream-parsing Title 1 and Title 40: PART (DIV5) `N` values are unique within each title (36 and 379 parts, no duplicates), and every SECTION (DIV8) sits inside a PART (0 orphans of 288 and 24,688). Stdlib `xml.etree.ElementTree.iterparse` parsed the 157 MB Title 40 in 3.2 s.
- NEW (verified 2026-10-30): `versions/title-{n}.json` is PAGINATED. `meta` = {result_count, page, per_page: 1000, total_pages}. Title 40 has 60,362 rows = 61 pages; one unpaginated call silently returns only page 1. `?page=N` works. `?part=60` and `?issue_date[gte]=2024-01-01` filters DO work here (unlike `chapter`). `per_page=5000` does not return content_versions.
- NEW: the earliest dates in the versions data are a bulk baseline load, not real changes. Title 1: 263 of 422 rows (62%) sit on 2015-12-18, and 74% of its sections first appear on that date. Title 40 page 1 shows a similar block on 2016-12-23/27. Counting these as "changes" would create a giant fake spike at the start of every chart.
- NEW: ~8–13% of version rows have substantive=false; removed=true rows exist (32 in Title 1).
- NEW (found while building): the versions `meta` counts are JSON **strings** (`"result_count": "60362"`, `"total_pages": "61"`), not numbers. The Rust downloader's first version assumed numbers and failed on every cold download.
- NEW: ecfr.gov rate-limits bursts with **HTTP 429 and no Retry-After header**. A cold nationwide download with 4 parallel workers hit it after ~60 s (about half the titles). The block lifted within a minute. All three downloaders now back off 5/10/20/40/60 s, and the Python ones use 2 workers.
- NEW: duplicate version rows (same title/type/identifier/date) are later editorial re-issues: same date, later `issue_date`, `substantive=false`.
- NEW: Title 41 Subtitle A (the only ref of `federal-procurement-regulations-system`) contains no parts, so that agency legitimately reports 0 words.
- ROUND 2 (verified 2026-10-30): authority notes are `<AUTH>` elements inside parts (8,229 of 9,659 parts; 274 parts have more than one, at subpart level; only 3 sit outside a part). With the contract regex: 99.0% of words are in parts citing a specific statute (7,956 parts), 0.4% cite only 5 U.S.C. 301 (100 parts), 0.2% only executive orders (87), 0.3% something unparsed (86, e.g. "18 U.S.C. appendix"), and 0.1% have no note (1,430 mostly empty/reserved parts, 90k words). Most-cited sections: 5 U.S.C. 301 (833 parts), 40 U.S.C. 486, 40 U.S.C. 121, 5 U.S.C. 552.
- ROUND 2: current sections from versions match the XML for Title 40 (24,688 sections exact; appendices 1,334 vs 1,336 in the XML, unresolved). Nationwide 231,300 current sections (contract rule: part must exist), 135,542 (58.6%) with no recorded change since before 2017. (An earlier preview said 231,324 because it counted 24 null-part rows; Codex caught it.)
- Starlette 0.46.2 `FileResponse` supports HTTP Range requests (relevant for DuckDB-WASM reading external Parquet).
- ROUND 3: TypeSafe's Jev is a closed, hosted API (early access, launched 2026-09-15 per a third-party guide); it can't be embedded. TurboJev (pypi, Apache-2.0) is an unrelated-looking local reproduction over GGUF models, unverified.
- ROUND 3: eCFR tables are `<TABLE>` elements (title 40: 9,566), equations `<MATH>` (1,847). Including them in sentence stats makes 7,695-word "sentences" (40 CFR 60). Prose-only, the longest is 1,051 words: real enumerations joined by semicolons.
- ROUND 3: Starlette `StaticFiles` returns 206 for Range requests on the Parquet store (verified with `curl -r 0-99`); DuckDB-WASM 1.29.0 from jsDelivr reads `/data/*.parquet` this way.
- ROUND 3: per-sentence regex classification over 109.6M words takes ~180 s in CPython (app ingest 249 s vs H2's 69 s).
- ROUND 4: daily change rate. `titles.json` showed 5 titles reissued on 10-27, 11 on 10-28, 8 on 10-29 (7%, 47% and 19% of all words), so most days a minority of titles change, and within them only a few parts.
- ROUND 4: historical full XML for a past date can 504 (Gateway Time-out) repeatedly for large titles: 2026-10-27 for titles 7, 40, 49 failed after many retries, while smaller titles succeeded. The incremental test therefore ran on the other 46 titles.
- ROUND 4: GitHub Pages returns 206 for Range requests with `Access-Control-Allow-Origin: *` (verified on pages.github.com); published sites max 1 GB; 10-minute deploy timeout. Python's `http.server` does NOT honor Range (returns 200), so use a Range-capable server for local DuckDB-WASM tests.
- ROUND 4: browsers cache `static/*.js|css`; asset URLs need a content hash (`?v=`), or a code-only redeploy is served stale.
- ROUND 4: DuckDB-WASM returns 128-bit integers (e.g. `sum()` results) as objects whose `toJSON()` is a quoted string; render them with `toString()`.
