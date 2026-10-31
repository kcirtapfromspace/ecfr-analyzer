# Brief for Codex: build H3 (Rust) of the eCFR analyzer

You are building one of three implementations that must return identical JSON. Claude is building H1 (Python+SQLite) and H2 (Python+DuckDB+Parquet) in parallel. A parity script will diff all three.

Read first, in this order: `CONTRACT.md` (normative; it wins over everything), `AGREED_PLAN.md` (context and rationale), `facts.md` (verified eCFR API behavior).

## Rules
- Implement everything in `h3/` (crate already set up). Build with:
  `cd h3 && CARGO_HOME=$PWD/.cargo cargo build --release --offline`
- Network is NOT available in your sandbox, and crates are pre-fetched. Use only the crates already in `h3/Cargo.toml`. You may remove crates you don't use. Do not add new ones.
- Storage: use SQLite via `rusqlite`. This mirrors H1, so the comparison isolates the language.
- **LOC budget: ≤ 850 code lines** for `h3/src/**` (counted by `tokei h3/src` after `cargo fmt`; blanks and comments excluded). The shared web UI takes ~350 of the 1,200-line limit. Write normal, readable, idiomatic Rust: no cramming, no giant one-liners, and leave `cargo fmt` output as is. If honest code needs more than 850 lines, stop at working code and report the real number. That number is the answer to the hypothesis.
- The downloader must exist and follow the contract (raw gzip body saved undecoded, versions pagination with the result_count assertion, temp-file + rename, import_in_progress check). It cannot run in your sandbox; the cache for titles 1, 40, 41 is already filled in `data/raw/2026-10-29/`, so `ingest` should get cache hits and never touch the network for those.
- Stream the XML (`flate2::read::GzDecoder` → `quick_xml::Reader`). Do not load whole files into a DOM; Title 40 is 157 MB uncompressed.
- Words: `[\p{L}\p{N}]+`, not `\w`. Rust's `\w` includes marks.
- The API server binds `127.0.0.1:{port}` and must handle concurrent requests safely (e.g. open a connection per request, or keep a `Mutex<Connection>`).

## Do
1. Implement `ingest` and `serve` per CONTRACT.md.
2. Run `h3/target/release/ecfr ingest --date 2026-10-29 --titles 1,40,41` from the repo root and report the wall time.
3. If your sandbox allows binding localhost, run `serve --port 8303` and curl each route once. If it doesn't, say so.
4. Run `cargo fmt`. If tokei is unavailable in your sandbox, count non-blank, non-`//` lines with a shell one-liner, and say which method you used.

## Report (final message, <= 300 words)
- Code-line count and method; per-file breakdown.
- Ingest wall time for titles 1, 40, 41; store size.
- Which routes you verified and how.
- **Every place CONTRACT.md was ambiguous or seemed wrong, and what you chose.** Do not silently resolve ambiguity; list it.
- Anything you could not do.
