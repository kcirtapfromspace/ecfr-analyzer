# Round 3 brief for Codex: independent oracle for the consolidated app

**Architecture change (please give your view):** we are consolidating into one build in `app/`, started from **H2** (DuckDB + Parquet), not H1. The reason is new since you agreed to "submit H1": the user wants DuckDB-WASM in the browser querying the store's Parquet files directly, so Parquet should be the single store (server DuckDB and browser DuckDB-WASM over the same files) instead of SQLite plus an export. If you disagree, say so in your report.

## Task
Write `app/tests/oracle.py`, an **independent** verifier for the CONTRACT.md section "Round 3" (prose text, sentence split, readability, sentence classifier, part staleness, ranking, the agency `readability`/`sentence_types`/`flagged_parts` fields, and `GET /api/candidates`). Build it **from the contract text alone**. You may reuse your own `h3/tests/verify.py`, but nothing from `app/`, `h1/` or `h2/`.

The oracle must:
1. Compute every round-3 value from the raw cache `data/raw/2026-10-29/` (XML + versions + agencies) for all non-reserved titles. Stdlib only (`xml.etree`, `re`, `unicodedata`, `math`, `json`).
2. `--dump expected.json`: write the expected round-3 values (per-agency `readability`, `sentence_types`, `flagged_parts`; the full ranked candidate list).
3. `--base http://127.0.0.1:PORT`: fetch `/api/agencies`, `/api/candidates?limit=500`, and `/api/candidates?agency=<slug>&limit=500` for every agency with at least one eligible part. Compare using the contract's comparison rule: exact ints and strings; floats within rel 1e-9 / abs 1e-12; ranks exact except swaps between parts whose scores are within tolerance. Print a summary of mismatches by field, with up to 3 examples each.
4. Run in your sandbox: `--dump` over the full cache (no network needed), plus any small self-checks on hand-made snippets for the splitter, classifier and syllables. Your sandbox can't reach localhost, so Claude will run the `--base` comparison.

Use `.venv/bin/python -I` (Python 3.12) from the repo root.

## Report (final message, <= 250 words)
- Your view on the architecture change (agree / disagree, one line why).
- Every contract ambiguity you hit and what you chose. **Don't silently resolve them.**
- Oracle runtime; N eligible parts; the top 5 candidates (title, part, score) from your dump.
- Code lines of oracle.py (tests are excluded from the LOC budget; just report it).
