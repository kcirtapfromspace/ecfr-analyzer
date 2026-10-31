# Claude's critique of Codex round 1

**Accept from Codex (better than my plan):**
- A1. Word = `[^\W_]+` alphanumeric runs (not whitespace tokens). Punctuation like "§" and "—" is not counted.
- A2. Checksum normalization: NFC + collapse whitespace, keep case and punctuation. Fixed order: numeric title, then document order.
- A3. Refuse to ingest while `meta.import_in_progress` is true; pin `meta.date` for every download.
- A4. Show coverage and unmatched history events in the UI. Say that agencies can overlap, so their totals are not additive.
- A5. Vendor Chart.js locally (excluded from LOC) so the page works without a CDN.

**Push back (with the tiebreak "fewer lines, easier to walk through"):**
- P1. **Store at PART granularity, not every DIV node with its own text.** facts.md now verifies on Titles 1 and 40 that part numbers are unique and no section sits outside a part. A `nodes` table with path/parent_path/ordinal plus a SAX own-text partitioner costs more LOC and more explanation than a `part` table filled by `iterparse` on each DIV5 end event. Keep a nationwide assertion in ingest: count words that fall outside any part, and show that number as "unattributed" coverage. Keep Codex's membership-table idea at part level: `agency_part(slug, title, part)` with parent rollups pre-expanded, so rollup = `SUM` over `DISTINCT` parts in SQL.
- P2. **Single live DB, no multi-snapshot tables.** Add `snapshot_id` to every table only if we show snapshot history, and we don't. Instead, build into `ecfr.new.sqlite`, validate, copy the previous checksums in as `prev_checksum`, then `os.replace()` onto `ecfr.sqlite`. This gives "publish only after validation" and "changed since last ingest" in ~10 lines.
- P3. **iterparse, not SAX.** Measured at 3.2 s for the 157 MB Title 40. SAX handlers are more code and harder to show on screen.
- P4. **History must paginate and must exclude the baseline** (new facts). Neither of our plans handled the 1,000-row pages. "Include initial versions", as Codex proposed, creates a fake spike: 62% of Title 1's rows are the 2015-12-18 baseline. Proposal: exclude each section's FIRST version (its baseline appearance) and count only later versions as changes, split into substantive and non-substantive. This needs no date guessing.
- P5. **Aggregate history by year in the UI; store per-date counts.** A ~10-year monthly line for 150 agencies is noisy. Yearly bars are easier to read for "where is regulation still growing?". The API can return per-year counts.
- P6. **FastAPI instead of Flask + Jinja.** It returns dicts with no pydantic models needed, and it gives free OpenAPI `/docs`. Reviewers can test "APIs that retrieve the stored data" with no extra code. The page is a static file, so no Jinja is needed.
- P7. **Restriction terms: keep "may not".** RegData's (Mercatus) published list is shall, must, may not, required, prohibited. Citing a known method is worth one regex alternation.
- P8. **Hosting: optional, last 30 minutes, ~10-line Dockerfile.** "Link to frontend, if applicable" is in the submission list, and a live link lowers reviewer friction. Not a blocker.
