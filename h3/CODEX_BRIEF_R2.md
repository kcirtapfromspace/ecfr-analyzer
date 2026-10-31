# Round 2 brief for Codex: authority tagging + staleness in H3

Context: H1/H2/H3 all return identical JSON on 636/636 routes over the full eCFR today. Claude is adding the same features to H1 and H2 in parallel. Afterwards, the parity script will diff all three again.

Read: `CONTRACT.md` (all of it, especially the new section "Round 2 additions" at the end, and the revised history de-dup key: part is in the key, and null part equals null part), and `facts.md` (lines marked ROUND 2).

## Do
1. Implement the Round 2 additions in `h3/src` exactly as specified in CONTRACT.md:
   - the `authority` tag and cites per part
   - `authority_words`, `sections`, `stale_sections`, `stale_share` on every agency object
   - `authority` on `top_parts` items
   - `top_statutes` on agency detail
   - `sections`, `stale_sections`, `authority_words` on `/api/meta`
2. Update **your own oracle** `h3/tests/verify.py` so it independently recomputes every new field from the raw XML and versions files, **from the CONTRACT.md text alone** (do not copy logic from h1/h2). If the contract is ambiguous anywhere, list it; don't silently choose.
3. Build: `cd h3 && CARGO_HOME=$PWD/.cargo cargo build --release --offline`. Then from the repo root run `h3/target/release/ecfr ingest --date 2026-10-29` (the full eCFR cache is already in `data/raw/2026-10-29/`, so this is offline and takes ~25 s). Then run your oracle against the store for all titles:
   `python3 -I -c "import sys,runpy; sys.path.insert(0,'h3/tests'); sys.argv=['verify.py','--titles','<all non-reserved titles>']; runpy.run_path('h3/tests/verify.py', run_name='__main__')"`
   Also run `cargo test` and `h3/tests/fixtures.py` (add fixture cases for the new tags if cheap).
4. `cargo fmt`.

## Rules
- No network; crates are pre-fetched; don't add crates (the `regex` crate is already there).
- **LOC ceiling: `h3/src` ≤ 900 code lines** by `tokei h3/src` after `cargo fmt` (it is 697 now; the shared web page grows to ~290, and the total limit is 1,200). Write normal, readable Rust. If honest code needs more, stop at working code and report the real number; that number is the answer to the hypothesis.
- Rust `regex` note: `\d` and `\s` are Unicode by default, the same as Python's `re` for str patterns, and the text is already whitespace-normalized.

## Report (final message, <= 250 words)
- Code-line count (tokei) and per-file breakdown.
- Nationwide ingest wall time.
- Oracle result: parts and responses verified, and any mismatches.
- Every contract ambiguity you found, and what you chose.
