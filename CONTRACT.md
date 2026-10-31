# Shared contract for H1 (Python+SQLite), H2 (Python+DuckDB+Parquet), H3 (Rust)

All three variants must produce **identical JSON** for the four API routes (checked by `bench/parity.py`). When this file and AGREED_PLAN.md disagree, this file wins.

## CLI (every variant)
- `ingest --date 2026-10-29 [--titles 1,40,41]`: download into the cache if needed, then build the variant's store. `--titles` defaults to every non-reserved title.
- `serve --port N`: serve the API plus `GET /` → `web/index.html` (shared file, read from disk).
- H1: `uv run h1/ecfr.py ingest|serve ...`. H2: `uv run h2/ecfr.py ingest|serve ...`. H3: `h3/target/release/ecfr ingest|serve ...`.
- Paths are relative to the repo root (`~/usds-ecfr`). Run from the repo root.

## Raw cache (shared; any variant may fill it; a cache hit means skip the download)
`data/raw/{date}/`:
- `agencies.json`: body of `GET https://www.ecfr.gov/api/admin/v1/agencies.json`
- `titles.json`: body of `GET https://www.ecfr.gov/api/versioner/v1/titles.json`
- `title-{n}.xml.gz`: body of `GET https://www.ecfr.gov/api/versioner/v1/full/{date}/title-{n}.xml`, requested with `Accept-Encoding: gzip` and stored **undecoded** (the gzip bytes as sent).
- `versions-{n}.json`: `{"result_count": int, "content_versions": [...]}`, merged from `GET https://www.ecfr.gov/api/versioner/v1/versions/title-{n}.json?page=P` for P = 1..meta.total_pages, rows in API order. The merged length MUST equal `meta.result_count` (fail the ingest otherwise).
- Write each file to a temp name, then rename it, so a crash never leaves a partial file that counts as a cache hit.
- Ingest fails if `titles.json` `meta.import_in_progress` is true.

Stores: H1 `data/h1/ecfr.sqlite`, H2 `data/h2/*.parquet`, H3 `data/h3/` (its choice). Build into a temp path, then replace, so a failed ingest keeps the old store.

## Parts (the unit of everything)
- A **part** is an XML element with `TYPE="PART"` (DIV5). Key: `(title int, part = its N attribute string)`.
- `ord` = 0-based index of the part among PART elements of its title, in document order.
- Ancestors: `subtitle` / `chapter` / `subchapter` = the `N` attribute of the nearest enclosing element with `TYPE` = `SUBTITLE` / `CHAPTER` / `SUBCHAP`; null if there is none. Keep them as strings (chapter `"0"` exists).
- **Normalized text** `T` of a part:
  1. Concatenate every text node inside the PART element (element text and the tails of its descendants, in document order, entities decoded, comments excluded), joined by a single space `" "`. Python: `" ".join(part_el.itertext())`.
  2. Apply Unicode NFC.
  3. Collapse every run of whitespace to one space and strip both ends. Python: `" ".join(s.split())`; Rust: `split_whitespace` joined by `" "`.
- `heading`: normalized text (same 3 steps) of the part's direct `HEAD` child; `""` if none.
- `words` = number of maximal runs of Unicode letters/digits in `T`. Python `[^\W_]+`; DuckDB/RE2/Rust `[\p{L}\p{N}]+`.
- `restrictions` = number of non-overlapping matches of `\b(shall|must|may not|required|prohibited)\b` in `lower(T)`.
- `hash` = lowercase hex SHA-256 of `T` encoded as UTF-8.

## Agencies
- Source: `agencies.json`. Top-level agencies have `children` (one level; no grandchildren). All 316 slugs are unique.
- A `cfr_reference` matches a part when `ref.title == part.title`, and for each key in `subtitle, chapter, subchapter, part` that is present in the ref, `ref[key] == part[key]` (exact string compare).
- **Own set** of an agency = parts matched by any of its own refs. **Set** used for all metrics = own set ∪ (for a top-level agency) the own sets of all its children. Each part counts once.
- For each agency: `words` = Σ words over the set, `restrictions` = Σ restrictions, `parts` = |set|, `density` = `1000.0 * restrictions / words` as an unrounded float (null if words == 0).
- `checksum` = lowercase hex SHA-256 of the UTF-8 concatenation of `"{title}|{part}|{hash}\n"` for each part in the set, ordered by title (numeric) ascending, then `ord` ascending. Null if the set is empty.
- `changed` = true only if a previous store existed, it had a non-null checksum for this slug, and that checksum differs from the new one. Otherwise false.

## History
- Rows: all `content_versions` of the ingested titles. Each row's `title` comes from the file name (int).
- De-duplicate on `(title, part, type, identifier, date)`. A merged row's `substantive` = OR of the duplicates and `removed` = OR. (Revised after the nationwide run: 139 keys in 13 titles list one appendix, e.g. a Title 14 SFAR, once per part under the same identifier and date. Each listing is a separate row attributed to its own part.) Rows with a null `part` (138 chapter-level appendices, e.g. "Appendix A to Chapter XIV") are kept, and null equals null when de-duplicating (SQL GROUP BY semantics). They match no agency because the unit is the part.
- Keep only rows with `date <= {snapshot date}`.
- **Baseline** rows: `date < "2017-01-01"`. **Change** rows: `date >= "2017-01-01"`.
- A row belongs to an agency if `(title, part)` is in the agency's set.
- Per agency and year (`int(date[0:4])`), count change rows:
  - `substantive` = not removed and substantive
  - `nonsubstantive` = not removed and not substantive
  - `removed` = removed
  - Omit years with no rows; sort by year ascending.
- `last_changed` = max `date` over the agency's de-duplicated rows (baseline included); null if none.

## API (compare parsed JSON; key order does not matter)
- `GET /api/meta` → `{"ecfr_date": str, "ingested_at": str (ISO-8601; parity ignores it), "titles": [int, ascending], "parts": int, "words": int, "unattributed_words": int, "baseline_rows": int, "change_rows": int, "unmatched_events": int}`
  - `words` = Σ over all parts. `unattributed_words` = Σ words of parts that are in no agency's own set.
  - `baseline_rows`/`change_rows` = counts of de-duplicated rows (all ingested titles).
  - `unmatched_events` = change rows whose `(title, part)` is not in the parts table.
- `GET /api/agencies` → JSON array of all 316 agencies `{"slug","name","short_name","parent_slug","words","restrictions","density","parts","checksum","changed","last_changed"}`, sorted by words desc, then slug asc. `short_name` is as given (it may be null or ""). `parent_slug` is null for top-level agencies.
- `GET /api/agencies/{slug}` → the same object plus `"refs"` (the agency's own `cfr_references`, verbatim, in source order), `"children"` (child slugs in source order; `[]` for children), and `"top_parts"` (up to 10 parts of the set `{"title","part","heading","words","restrictions"}`, sorted by words desc, then title asc, then ord asc). Unknown slug → HTTP 404 with body `{"detail":"not found"}`.
- `GET /api/agencies/{slug}/history` → `{"slug": str, "years": [{"year": int, "substantive": int, "nonsubstantive": int, "removed": int}]}`. Unknown slug → 404 as above.
- `GET /` → contents of `web/index.html` as `text/html`.

## Round 2 additions: authority tagging and staleness (the scatter plot is page-only)

### Authority (per part)
- **Authority text** `A`: for every element named `AUTH` inside the PART, in document order, take its normalized text (the same 3 steps as `T`), then join those with `" "`. `A = ""` if there are none. (Only 3 `AUTH` elements in the whole eCFR sit outside a part; ignore them.)
- **Cites** = the set of distinct strings `"{g1} U.S.C. {g2}"` over all matches of the case-sensitive regex `(\d+)\s*U\.\s*S\.\s*C\.?\s+(\d+[A-Za-z]*)` in `A`. Known limitation: only the first section after each "N U.S.C." is captured, so "5 U.S.C. 301, 552" yields only `5 U.S.C. 301`.
- **authority** tag: the first rule that applies.
  1. `none`: `A == ""`
  2. `statute`: cites contains anything other than `"5 U.S.C. 301"`, or `A` matches `Pub\.\s*L\.|Public Law`
  3. `housekeeping`: cites is non-empty (so it is exactly {"5 U.S.C. 301"}, the general Housekeeping Statute)
  4. `executive`: `A` matches `E\.\s*O\.|Executive Order|Proclamation|Reorganization Plan`
  5. `other`
- All regexes are case-sensitive. These are descriptive tags of what the authority note cites. They are not legal conclusions about whether a rule is mandatory.

### Staleness (from the de-duplicated version rows)
- Section key: `(title, part, type, identifier)`. Its **latest row** is the de-duplicated row with the max `date` (unique, because date is part of the de-dup key).
- A section is **current** if its latest row has `removed == false` and its `(title, part)` is in the parts table.
- A current section is **stale** if its latest row's `date < "2017-01-01"`, i.e. no recorded change since eCFR history began. This is the same empirical cutoff as the history chart; it is not a verified "10 years".

### New API fields (unrounded floats; null when the denominator is 0)
- In every agency object (list and detail):
  - `"authority_words"`: `{"statute": int, "housekeeping": int, "executive": int, "other": int, "none": int}`, with all five keys always present. Each is Σ words of the set's parts with that tag.
  - `"sections"`: count of current sections whose `(title, part)` is in the set.
  - `"stale_sections"`: count of those that are stale.
  - `"stale_share"`: `stale_sections / sections`.
- `top_parts` items gain `"authority"` (the tag).
- Agency detail gains `"top_statutes"`: up to 10 `{"cite": str, "parts": int, "words": int}` over the parts in the set. `parts` = number of set parts whose cites contain `cite`; `words` = Σ their words. Sorted by words desc, then cite asc by byte (codepoint) order.
- `/api/meta` gains `"sections"` and `"stale_sections"` (all current sections), plus `"authority_words"` (same 5 keys, over all parts).

## Round 3: consolidated app (`app/`), readability, sentence classifier, ranking

Architecture: one build in `app/`, started from H2. Parquet is the single store: the server queries it with DuckDB, and the browser queries the same files with DuckDB-WASM. The four JSON routes above stay unchanged, plus new fields. H1/H2/H3 are frozen as measured.

### Prose and sentences (per part)
- **Prose text** `P`: the same steps as `T`, except that text inside elements named `TABLE` or `MATH` (and their descendants) is skipped. The *tail* text after such an element is kept. Python: yield `el.text`; for each child, recurse (yielding nothing if the child is TABLE/MATH), then yield `child.tail`. Join the pieces with " ", then NFC, collapse whitespace, strip.
- **Sentence split** of `P`:
  1. Split at every whitespace run that is immediately preceded by `.`, `?` or `!` and immediately followed by one of `A-Z ( § " “`. Python: `re.split(r'(?<=[.?!])\s+(?=[A-Z(§"“])', P)`.
  2. Re-join a piece to the previous kept piece (with one space) when the previous kept piece ends with an abbreviation: it matches `(?:^|[\s(])(?:U\.S\.C|U\.S|e\.g|i\.e|etc|et seq|No|Nos|Sec|Secs|Pub|L|Stat|Fed|Reg|Inc|Co|Corp|Ltd|Dr|Mr|Mrs|Ms|St|Jr|Vol|Ch|Pt|App|cf|al|approx|ft|in|lb|lbs|oz|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|[A-Z])\.$` (case-sensitive).
  3. Drop pieces with no word (WORD regex). The rest are the **sentences**. The split is approximate by design.
- A sentence's word count uses the WORD regex.

### Readability (per part, all from `P` and its sentences)
- `prose_words` = WORD count of `P`. `sentences` = number of sentences. `long_sentences` = sentences with more than 40 words.
- `syllables` = Σ over WORD matches `w` in `P` of max(1, number of maximal runs of `[aeiouy]` in lower(w)).
- `passive_sentences` = sentences where lower(sentence) matches `\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?\w+(?:ed|en)\b` (each sentence counts at most once).
- `crossrefs` = number of matches in lower(P) of `§|\bparagraphs? \(|\bsections? \d|\bparts? \d|\bsubparts? [a-z]\b|u\.s\.c\.`.
- Derived, null when the denominator is 0:
  - `words_per_sentence` = prose_words / sentences
  - `fk_grade` = 0.39 × prose_words / sentences + 11.8 × syllables / prose_words − 15.59 (Flesch–Kincaid grade, approximate syllables)
  - `long_share` = long_sentences / sentences
  - `passive_share` = passive_sentences / sentences
  - `crossrefs_per_1k` = 1000 × crossrefs / prose_words

### Sentence classifier (per sentence, on lower(sentence); the first rule that matches wins, in this order)
1. `definition`: `\b(?:means|is defined as|has the meaning|have the meaning|as used in this)\b`
2. `prohibition`: `\b(?:shall not|must not|may not|is prohibited|are prohibited|prohibited from|no person shall|no person may)\b`
3. `paperwork`: matches `\b(?:shall|must|is required to|are required to)\b` **and** `\b(?:report|reports|record|records|recordkeeping|submit|submits|submitted|notify|notification|certify|certification|application|apply|file|filing|disclose|disclosure|form|forms)\b`
4. `obligation`: `\b(?:shall|must|is required to|are required to|required)\b`
5. `permission`: `\bmay\b`
6. `other`
- Per part, store the six counts (they sum to `sentences`). This is a transparent, deterministic stand-in for an ML classifier, and an approximate one: e.g. epistemic "may be present" counts as permission.

### Part staleness
- `part_sections` / `part_stale` = current / stale sections (the round-2 definitions) whose `(title, part)` is this part. `part_stale_share` = part_stale / part_sections (null if 0).

### Ranking (review candidates; parts only)
- **Eligible**: parts with `words >= 1000` and `sentences > 0`. Call the count N.
- Six inputs per eligible part:
  - `size` = log10(words)
  - `density` = 1000 × restrictions / words
  - `grade` = fk_grade
  - `directive` = (prohibition + paperwork + obligation) / sentences
  - `paperwork` = paperwork / sentences
  - `staleness` = part_stale_share, with null treated as 0
- For each input, z = (x − mean) / std over the eligible parts, using the **population** std; if std = 0 then z = 0. `score` = mean of the six z values (equal weights).
- `rank` = 1..N, ordered by score desc, then title asc, then ord asc. `flagged` = rank ≤ ceil(0.10 × N).
- These are "review candidates", not findings of over-regulation.

### API additions (floats unrounded; null when the denominator is 0)
- Every agency object gains:
  - `"readability"`: `{"sentences", "words_per_sentence", "fk_grade", "long_share", "passive_share", "crossrefs_per_1k"}`, computed from the **sums** of the part counts over the set (fk_grade from the summed prose_words, sentences and syllables)
  - `"sentence_types"`: `{"definition", "prohibition", "paperwork", "obligation", "permission", "other"}`, the summed counts
  - `"flagged_parts"`: the number of flagged parts in the set
- `GET /api/candidates?agency=<slug>&limit=<n>` (limit default 50, clamped to 1..500) → `{"agency": slug or null, "eligible": N, "flagged": ceil(0.10 × N), "candidates": [...]}`. Candidates are eligible parts (in the agency's set if `agency` is given) in rank order, up to `limit`. Each item is `{"rank", "title", "part", "heading", "words", "score", "flagged", "inputs": {six raw values}, "z": {six z values}}`. An unknown agency gives a 404 like the other routes.
- **Comparison rule for verification**: integers and strings exact; floats within relative tolerance 1e-9 (absolute 1e-12 near 0); ranks exact, except that parts whose scores are within tolerance of each other may swap.
- `GET /data/<file>.parquet` serves the store files (HTTP Range supported) for DuckDB-WASM: `parts.parquet` (metrics, no text), `parts_text.parquet` (title, part, text), `agencies.parquet`, `agency_parts.parquet`, `versions.parquet`.

## Round 4: daily incremental refresh, history, static site (GitHub Pages)

### Store layout (`--store`, default `data/app`; the `data` branch holds exactly this)
`parts.parquet` (metrics + ranking, no text) · `text/title-{n}.parquet` (title, part, text: split per title) · `versions.parquet` (rows with date <= snapshot) · `versions_all.parquet` (every row the API returned; state for deltas) · `agency_parts.parquet` · `agencies.parquet` · `agency_history.parquet` · `part_changes.parquet` · `meta.json` · `titles.json` (the catalog of the last run; state).

### Incremental ingest (default when a store exists; `--full` reprocesses everything)
- Snapshot date = `--date`, else `titles.json` `meta.date`. If the store is already at that date with the same titles, the run is a no-op.
- A title is **reprocessed** if it is new, if its (`latest_amended_on`, `latest_issue_date`) differs from the stored catalog, or if any stored version row has `previous_date < date <= new_date` (an amendment taking effect can change text without moving the catalog dates). Other titles keep their stored rows and text file unchanged.
- Versions for a reprocessed title: `?issue_date[gte]=<previous ecfr_date>` (all pages), merged into `versions_all` with the round-1 de-dup key and OR rule. The snapshot filter `date <= snapshot` applies at compute time, not at ingest.
- Sentence metrics are reused per part when (part, SHA-256 of the prose text `P`) matches the stored row **and** the stored `metrics_version` equals the code's `METRICS_VERSION`; otherwise they are recomputed. A version mismatch forces a full run.
- All analytics (agency rollups, checksums, staleness, ranking) are recomputed over all parts every run.
- Equivalence requirement: an incremental update from D1 to D2 must produce the same API output as a full build at D2 (ints/strings/ranks exact; floats within the round-3 tolerance), except `changed`, `meta.mode`, `meta.previous_ecfr_date`, `meta.titles_processed`, `meta.parts_changed`, and the history routes.

### History (append-only)
- `agency_history`: one row per agency per snapshot `(ecfr_date, slug, words, restrictions, parts, checksum, sections, stale_sections, flagged_parts)`; rerunning a date replaces that date's rows.
- `part_changes`: `(ecfr_date, title, part, heading, change ∈ {added, modified, removed}, words_before, words_after)`, by comparing part text hashes with the previous store. Recorded only when the snapshot date moves forward; those rows replace any earlier rows for the same date.

### API additions
- `meta` gains `metrics_version`, `mode` (`full`|`incremental`), `previous_ecfr_date`, `titles_processed`, `parts_changed` `{added, modified, removed}`.
- `GET /api/agencies/{slug}/trend` → `{"slug", "days": [{"date", "words", "restrictions", "parts", "checksum"}]}` ordered by date.
- `GET /api/changes?limit=` (default 200, 1..1000) → `{"changes": [...part_changes rows...]}` ordered by date desc, title, part.

### Static site (`export --out site`)
- `api/meta.json`, `api/agencies.json`, `api/agencies/{slug}.json`, `api/agencies/{slug}/history.json`, `api/agencies/{slug}/trend.json`, `api/candidates.json` (top 500), `api/candidates/{slug}.json` (top 500), `api/changes.json` (200), `api/openapi.json`. Each file parses equal to the live route's response. A missing file is GitHub Pages' HTML 404, not JSON.
- `index.html`, `ui/agency/{slug}.html`, `ui/candidates/{slug or all}.html` (htmx fragments), `static/` (asset URLs carry a content hash), `data/` (the store minus state files).
- All URLs are relative, so the site works under `/<repo>/`. Sorting and search run in the browser.
