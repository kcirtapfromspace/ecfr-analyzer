# Three hypotheses, measured

All numbers come from the full eCFR as of 2026-10-29 (49 titles, 9,659 parts, 109.6 M words, 485,698 version rows), with a warm download cache, on a 20-core Mac Studio. Raw logs are in `bench/results/`. Re-run with `bench/bench.sh 2026-10-29`.

**Correctness:** all three variants return **identical JSON on 636/636 routes** (`bench/parity.py`: meta, the agency list, and every agency's detail and history, plus 404s). Codex's independent stdlib-Python oracle (`h3/tests/verify.py`, sharing no code with H1/H2/H3) recomputes all 9,659 parts and 634 responses from the raw files and matches H3 over HTTP, with no regex word-boundary differences. H3's `cargo test` and fixture tests pass after the fixes.

| | H1 Python + SQLite | H2 Python + DuckDB + Parquet | H3 Rust + SQLite |
|---|---|---|---|
| Code lines (tokei; backend + shared `web/` 223) | 318 + 223 = **541** | 315 + 223 = **538** | 697 + 223 = **920** |
| Fits the 1,200-line limit | yes (45%) | yes (45%) | **yes (77%)** |
| Ingest, warm cache: wall / peak memory | 53.6 s / 1.13 GB | 64.9 s / 2.13 GB | **22.3 s / 0.55 GB** |
| Store | 45 MB SQLite (metrics + hashes) | 152 MB Parquet (metrics + **full normalized text**) | 47 MB SQLite (precomputed JSON responses) |
| Median latency via curl (~10 ms is curl's own floor): list / EPA detail / EPA history | 16.7 / 12.8 / 38.1 ms | 16.5 / 15.8 / 23.7 ms | 11.3 / 11.0 / 10.6 ms |
| Server memory | 132 MB | 211 MB | 10 MB |
| Dependencies | 12 PyPI packages | 13 PyPI packages | 184 crates, 8.5 MB binary, ~25 s clean dependency build |
| Cold download (Title 1, own downloader) | ok | ok | ok (after fix a) |

Line counts are code lines only: blanks, comments, tests and benchmark scripts are excluded, and Python is formatted with `ruff format --line-length 100` to match rustfmt's width. H3 also has 465 lines of tests (excluded). Formatter differences between Python and Rust stay a judgment call.

## Recommendation (Claude and Codex agree)
- **Submit H1.** It is the lightest to explain on a screen-share. It has the lowest memory of the Python variants, the same line count as H2, and no tuning knobs.
- **H2's idea worth keeping:** store the normalized text in Parquet (152 MB with zstd). New text metrics then become a SQL query instead of a re-parse. Add it as an extension only if a custom metric needs it.
- **H3:** Rust fits easily (920 lines) and is 2.4× faster to ingest, with a 13× smaller server. At this data size, reviewers won't see that difference. Choose it to showcase Rust, not for the numbers.
- Codex first agreed to H2, on the condition that its ingest memory be capped. After the cap, H2 lost its speed edge and its "all analytics in SQL" property. When asked again with the new numbers, Codex agreed to H1 ("No required change").

## What the build found (none of it was visible on the 3-title sample)
1. **The versions API sends counts as strings** (`"result_count": "60362"`). H3 assumed numbers and failed every cold download. This was a gap in Claude's facts/contract; H3 is fixed.
2. **ecfr.gov rate-limits with HTTP 429 and no Retry-After.** The first nationwide download (4 workers) died after ~60 s. All three now back off 5/10/20/40/60 s, and the Python variants use 2 workers.
3. **One appendix can be listed under several parts** (139 keys in 13 titles, e.g. a Title 14 SFAR under 8 parts). H3's fail-loud check caught it; H1 had silently merged the rows. The de-duplication key now includes `part`.
4. **138 chapter-level appendices have no part.** SQLite treats NULLs in a key as distinct, DuckDB as equal, so H2's meta counts differed by 11–22 rows until the contract pinned "null equals null".
5. **DuckDB HUGEINT sums became floats in Parquet** (185051 → 185051.0). Fixed with a BIGINT cast.
6. **H2 memory** was 3.7 GB. Four separate causes: an in-memory build DB, a 1 GB JSON object buffer per thread, a single Parquet row group holding all text, and `regexp_extract_all` lists over 109 M words. Fixing them cost ingest speed (43 s → 65 s).
7. Validated nationwide: part numbers are unique (primary key); only 0.08% of words fall outside parts; every title's baseline ends by 2016-12-31, so the 2017 cutoff holds; and only two agencies match no parts, both genuinely empty (Title 41 Subtitle A, Title 15 Chapter XIII).

## Changes from AGREED_PLAN.md
- Chart.js loads from a pinned CDN URL with an SRI hash instead of a vendored file, so each server serves one file.
- History de-duplication key: `(title, part, type, identifier, date)`, with null part equal to null part (see CONTRACT.md).
- Known methodology effect: OR-merging same-date editorial re-issues folds most non-substantive rows into substantive ones, so the "non-substantive" series is near zero.

## Who did what
- **Claude:** API probing, `facts.md`, `CONTRACT.md`, H1, H2, `web/index.html`, the parity and benchmark harness, all nationwide runs, and four post-hand-off fixes to H3 (1–4 above), which Codex reviewed and approved, plus the matching key change in `h3/tests/verify.py`.
- **Codex:** H3 (Rust) built in its sandbox from `h3/CODEX_BRIEF.md` against the contract, with its own tests (`h3/tests/`). It reviewed Claude's H3 fixes and the recommendation in two rounds.
- Process: independent plans → mutual critique → agreed plan → shared contract → parallel builds → parity → nationwide benchmark → joint recommendation.

## Reproduce
```sh
cd ~/usds-ecfr
uv run h1/ecfr.py ingest --date 2026-10-29        # fills data/raw/ on first run (~2 min)
(cd h3 && CARGO_HOME=$PWD/.cargo cargo build --release --offline)
bench/bench.sh 2026-10-29                                       # ingests all three, parity, latency
```

# Round 2: authority tagging, scatter plot, staleness

Definitions are in CONTRACT.md ("Round 2 additions"). Claude built H1, H2 and the page; Codex built H3 and extended its own oracle from the contract text alone. Codex found no contract ambiguities, and it caught one wrong count in Claude's facts (231,324 → 231,300 current sections).

**Correctness:** all three are identical on 636/636 routes. Codex's oracle also verified **each server directly over HTTP** (9,659 parts and 634 responses each), with zero mismatches.

| | H1 Python + SQLite | H2 DuckDB + Parquet | H3 Rust |
|---|---|---|---|
| Code lines (backend + shared web 269) | 378 + 269 = **647** | 372 + 269 = **641** | 822 + 269 = **1,091** |
| Share of the 1,200 limit | 54% | 53% | **91%** |
| Ingest wall / peak memory | 57.9 s / 1.14 GB | 69.4 s / 2.0–2.6 GB (varies by run) | 24.3 s / 0.55 GB |
| Store | 49 MB | 152 MB | 48 MB |
| Median latency: list / EPA detail / EPA history | 23 / 16 / 39 ms | 23 / 22 / 26 ms | 13 / 12 / 12 ms |
| Server memory | 132 MB | 235 MB | 10 MB |

**Hypothesis 3 under growth:** Rust still fits, at 91% of the budget (1,091/1,200). Round 2 added 171 lines in total, so at the current implementation's growth rate another round like it would exceed 1,200 before refactoring. Codex, who wrote H3, says 822 is lean but not the honest minimum: it has unmeasured refactoring slack (unused persisted fields, sorting machinery, repeated XML plumbing). The Python variants still have ~550 lines of room.

**Round-2 sign-off:** Codex AGREES with the unchanged recommendation (submit H1; H2's Parquet text store optional; H3 to showcase Rust). Its one required change, the growth-claim wording above, is applied.

**What the new metrics show (full eCFR):**
- 99.0% of regulatory words sit in parts whose authority note cites a specific statute. Only 0.4% cite just 5 U.S.C. 301, 0.2% only executive orders, and 0.1% have no note. Agency-level "non-statutory" shares are therefore near zero, so the useful output is **which statutes drive the most text**.
- EPA: 42 U.S.C. 7401 (Clean Air Act) underpins 11.2 M of its 18.1 M words (61.8%).
- Limitation: authority notes also cite procedural statutes. Labor's most-cited section is 5 U.S.C. 553 (APA notice-and-comment) at 34% of its text. The list shows what a rule *cites*, not what *mandates* it. Excluding procedural cites (5 U.S.C. 552/553) is a possible refinement.
- 58.6% of the 231,300 current sections have no recorded change since eCFR history began (2017 cutoff). The range is wide: Commerce 19.8%, Transportation 45.5%, EPA 65.9%, Justice 74.4%, Social Security 82.4%.
- The scatter plot (words on a log scale vs. restriction density, with median guides) puts large, directive rulebooks in the upper right. It is page-only, so it doesn't count toward any backend.

# Round 3: consolidated app (htmx + DuckDB-WASM over Parquet), readability, sentence classifier, ranking

**Architecture:** one build in `app/`, started from H2. Parquet is the single store: the server queries it with DuckDB, and the browser queries the same files with DuckDB-WASM over HTTP Range requests. Pages use htmx fragments rendered by Jinja from the same query functions as the JSON API. All four original JSON routes are kept, plus `GET /api/candidates`. Codex agreed with consolidating on H2 instead of H1 ("one Parquet store supports server DuckDB and browser DuckDB-WASM without export drift"). H1/H2/H3 stay frozen as the measured experiments.

**Jev:** TypeSafe's Jev is a closed, hosted, early-access API, so it can't be embedded. The app uses a transparent rule-based sentence classifier instead (definition / prohibition / paperwork / obligation / permission / other; first match wins). A local GGUF model over the top-ranked candidates (the Jev pattern) is a possible later layer.

**Verification:**
- Codex's independent oracle (`app/tests/oracle.py`, 459 lines, written from CONTRACT.md alone) recomputed everything from the raw XML: 9,659 parts, 6,402 eligible, 641 flagged. Against the live app it found **0 mismatches** across every agency's readability/sentence types/flagged count, the global ranking, and 297 per-agency candidate routes.
- The round-1/2 fields equal the verified H1 on 635 routes. `changed` is excluded because it depends on each store's previous ingest.
- In a real browser: all htmx interactions work (agency detail swap with chart re-init, candidate filter, search across sub-agencies, sort), and a DuckDB-WASM query returns 20 rows in 726 ms from `/data/parts.parquet`, with HTTP 206 Range responses confirmed.

| Consolidated app | |
|---|---|
| Code lines (tokei, tests excluded) | **936** = Python 626 + templates 154 + JS 100 + CSS 56 (78% of 1,200) |
| Full-eCFR ingest | 249 s / 2.28 GB peak (sentence processing adds ~180 s over H2) |
| Store | `parts.parquet` 1.4 MB (metrics, for the browser), `parts_text.parquet` 140 MB, `versions` 2.8 MB, `agencies` 53 KB |
| Latency (median, curl) | page 22 ms, /api/agencies 29 ms, agency detail fragment 41 ms, candidates 19–30 ms |
| Server memory | 212 MB |

**Findings:**
- Sentence splitting needs tables excluded: with `<TABLE>`/`<MATH>` included, 40 CFR 60 had a 7,695-word "sentence"; prose-only, the longest is 1,051 words (real "(1) …; (2) …" enumerations).
- Example readability (Labor): Flesch–Kincaid grade 17.6, 30.5 words per sentence, 23% of sentences over 40 words, 37.7% passive. Sentence types: 26.5% obligation, 5.6% paperwork, 3.5% prohibition.
- **The ranking is dominated by paperwork share.** That input is long-tailed (z up to +7.7), so under equal weights the top candidates are short reporting/recordkeeping parts (11 CFR 108, 29 CFR 403, 9 CFR 320, 8 CFR 247, 29 CFR 402). That is defensible for paperwork-burden reduction, but it is a weighting effect. **Option for the user:** cap each z at ±3 (a one-line change plus an oracle update; Codex prefers this to percentile ranks, which change the model more broadly).

**Round-3 sign-off:** Codex AGREES: submit the consolidated app, keep H1–H3 as documented experiments, and present the z-cap as the user's choice. No required change.

# Round 4: daily refresh on GitHub Actions, history, and a static site on GitHub Pages

**Best of each version:** H2's Parquet store (now the only store), H3's idea of precomputing every response (now the static JSON export), and H1's simple stdlib downloader. The Rust speed-up is not needed: the daily run only redoes the slow sentence analysis for parts whose prose text changed.

**How a daily run works** (`.github/workflows/daily.yml`, 49 lines):
1. Restore the store from the `data` branch. If the branch is absent, that's the first run; any other git failure stops the run rather than starting a fresh history.
2. `ingest`: fetch `titles.json`; reprocess only titles whose catalog dates moved or whose stored versions took effect since the last run; download only those titles; reuse sentence metrics for unchanged prose; fetch only versions issued since the last run.
3. `export`: write the static site (JSON API + OpenAPI, htmx fragments, Parquet with text split per title).
4. Force-push the store as one commit to `data`; history lives inside `agency_history.parquet` and `part_changes.parquet`, so the branch never grows.
5. Deploy to GitHub Pages. Sundays run `--full` as the safety net.

**Measured (46 titles; 3 large titles excluded because ecfr.gov returned 504 for their 2026-10-27 XML):**

| | Full build | Incremental 10-27 → 10-29 |
|---|---|---|
| Wall time | 190 s | **34 s** (16 titles reprocessed, 24 parts changed) |
| Peak memory | 1.9 GB | 1.6 GB |
| Same-day rerun | | no-op ("store is already at eCFR 2026-10-29") |

Full 49-title ingest: 246 s / 2.1 GB. Export: ~7 s for 1,961 files. Site: 156 MB (text 134 MB in 49 files, largest 19 MB; `parts.parquet` 1.7 MB), within Pages' 1 GB limit.

**Verification:**
- **Incremental == full:** all 951 non-history JSON files of an incremental 10-27→10-29 update equal a fresh full 10-29 build (ints, strings and ranks exact; floats within 5.4e-11).
- **Static == live:** each static JSON file parses equal to the matching live API response (1,268 pairs).
- **Codex's oracle** (built from CONTRACT.md alone): 0 mismatches on the full 49-title build.
- **Browser, under a `/ecfr-analyzer/` subpath with a Range-capable server (as on Pages):** every table sorts with ▲/▼ (including Review candidates, which could not sort before); search finds sub-agencies; the agency filter, agency detail (with the new size-over-time chart) and the "What changed" panel work; DuckDB-WASM queries the per-title text view `parts_text` and the history files.

**Codex review:** it disagreed and required two changes, plus two edge fixes; all four were applied and re-verified:
1. A failed clone was treated as "no data branch", which could wipe history. Now only an absent branch (exit 2) starts fresh.
2. A run narrowed with `--titles` kept other titles' version rows. Now filtered.
3. The live server shadowed `/api/agencies/<slug>.json`. Now answered.
4. Backdated or repeated dates could log reversed or duplicate changes. Now changes are logged only when the date moves forward, replacing that date's rows.
Codex had earlier also changed the design itself: reprocess titles whose stored versions take effect between runs, and key sentence-metric reuse on the prose hash plus a metrics version.

**Other bugs found while testing:** a "What changed" column that did not wrap pushed the whole page sideways; a cached `app.js` survived redeploys (fixed with content-hashed asset URLs); and DuckDB-WASM's 128-bit integers rendered as quoted strings.

**Size:** app 1,151 code lines (Python 799, templates 172, JS 123, CSS 57) + workflow 49 = **1,200**. Getting there took real simplifications (one schema string, a shared catalog helper, flattened history files), not cramming. One cosmetic CSS rule was dropped.

**Not done (needs the user):** create the public repo, push, set Pages to "GitHub Actions", run the first full build. Scheduled workflows in public repos can be auto-disabled after long repository inactivity; check whether the daily data-branch push keeps the schedule alive.

## Deployment (2026-10-31)
- Public repo: https://github.com/kcirtapfromspace/ecfr-analyzer · site: https://kcirtapfromspace.github.io/ecfr-analyzer/
- First Actions run (workflow_dispatch, no `data` branch yet, so a full build): every step succeeded in about 9 minutes. The live site, the static API and Parquet Range requests (206 from the Pages CDN) all checked out.
- Python tooling is uv only: CI uses `astral-sh/setup-uv` with `uv run --with-requirements app/requirements.txt`; there is no pip.
- An automated security review flagged that `export` builds file paths from agency slugs, which come from eCFR data. Real slugs contain `'`, `(`, `)` and `,`, so a strict slug pattern would break 9 agencies. Instead, `write()` refuses any path that resolves outside the output directory.

# Round 5: composable components

The single `app/ecfr.py` became the package `app/ecfr/`. Code moved verbatim by AST line ranges, not retyped. The `STORE` global is gone: the store path is a parameter everywhere, so each module works on its own (e.g. `from ecfr.text import readability`).

| Module | Lines | Responsibility | Depends on |
|---|---|---|---|
| `source.py` | 72 | eCFR API client, raw cache, catalog dates | stdlib |
| `text.py` | 90 | Metrics on strings: words, restriction terms, authority tags, sentences, readability | stdlib |
| `parse.py` | 54 | Stream a title's XML into part rows (reuses unchanged sentence metrics) | text |
| `model.py` | 3 | Definitions shared by the build and the read layer | — |
| `build.py` | 309 | DuckDB build: incremental ingest, analytics, ranking, history, meta | source, parse, text, model |
| `queries.py` | 130 | Read queries shared by the API and the export | text, model |
| `site.py` | 102 | Static export; owns `templates/` and `static/` | queries, source |
| `api.py` | 37 | FastAPI `create_app(store, site)` and `serve` | queries, source |
| `cli.py` | 33 | The `ecfr` console script | build, site, api |

- The dependency graph is acyclic and points one way: data in → build → read → outputs.
- Packaging moved to `pyproject.toml` + `uv.lock` (uv only; `requirements.txt` removed). Run it with `uv sync` then `uv run ecfr …`; CI uses `uv run --frozen --no-dev ecfr …`.

**Equivalence (the refactor changes no output):**
- The new code's export of the current store is identical to the old one on all 1,961 files (JSON parse-equal, HTML byte-equal).
- A new-code 46-title rebuild (10-27 full → 10-29 incremental) equals the old-code result on all 1,269 API files including history (floats within 1.8e-11).
- The live API equals the static files.
- Codex reviewed it and agreed, with no required changes. Its one suggestion, moving shared constants out of `build.py` so the read layer doesn't load ingest code, was applied (`model.py`) and re-verified.

**Size:** app 1,183 code lines (was 1,151; imports and module docstrings account for the difference) + workflow 48 + `pyproject.toml` 15 = 1,246. The app code alone is under 1,200; counting CI and packaging config, it is 46 over. Getting the total back under would mean dropping a requested feature (e.g. the scatter plot, ~30 lines, or the SQL explorer, ~45 lines), which is the user's call.

# Round 6: frontend evaluation (htmx, raw JS, SvelteKit, Observable Framework, VanJS, Preact)

Each candidate implemented the same slice (agency table with sort and search, scatter plot, detail with history chart) from the same fixture JSON and passed one shared Playwright test under the `/ecfr-analyzer/` subpath. Full tables are in [frontends/RESULTS.md](frontends/RESULTS.md); the code is in `frontends/`.

- **SvelteKit (lean)** won on what was asked for: tests, type checks (template-level, plus a11y) and the lightest first view (114.8 KB gzip). It was the user's first choice and Codex's independent pick. Its cost is about 1.4× the lines plus a Node toolchain.
- **Raw JS + JSDoc** had htmx's line count, no build step, and `tsc --checkJs` caught the planted field typo. VanJS and Preact were no better under the cap.
- **Observable Framework** was 3.4× heavier with no type checks in pages; **htmx** was weakest on tests and types.

# Round 7: Checkpoint 2: the raw-JS port measured; htmx kept

The agreed rule (Codex's condition) was to build the complete port, enforce 1,200 lines in CI, and keep htmx if it can't fit. The decision record is [DECISIONS.md](DECISIONS.md) (D7).

**The port** (branch `raw-js-port`) replaced Jinja/htmx with ES modules, using:
- an escaping `html` tag
- one sortable-table component
- hash routing to agency details
- a trimmed `api/agency-table.json`, about a fifth of `agencies.json`
- `ui/candidates/*.json` files of 25 rows

It passed `tsc --checkJs`, the shared slice e2e and a browser check (filter, sort, detail charts, sub-agency links, back button, slugs with `'`, `(`, `)` and `,`, 404s, DuckDB explore).

| | htmx (shipped) | raw JS port |
|---|---|---|
| App code lines (tokei) | **1,176** | 1,228 (28 over) |
| First view, gzip (same store) | 126.5 KB / 5 requests | 102.5 KB / 13 requests |
| Agency detail, gzip | 3.1 KB | 6.3 KB |

- **The user chose htmx**, which stays under 1,200, over shipping the port at 1,228 or cutting a feature.
- **Kept from the attempt:**
  - A CI workflow: lint, oracle self-tests, the line gate, and an e2e test of the shipped UI against the real store. The e2e takes its expected values from the exported JSON, so daily data changes don't break it, and it fails when header sorting is broken (checked by breaking it).
  - Duplicated SQL removed from `build.py` (the generated SQL is byte-identical to v0.1.0's).
  - `ruff` settings pinned in `pyproject.toml`.
- **Measurement pitfalls found:**
  - tokei doesn't parse regex literals, so a quote inside one makes it count the following comments as code. In the port this was 32 lines; in the shipped `app.js` it is 3, and we report tokei's higher number.
  - ruff 0.17 enables about 400 lint rules by default, and its default line length (88) reflows the code. Both are now pinned.
- **Verification on the release:**
  - Codex's oracle: 0 mismatches against the live API (agencies, global candidates, 297 agency candidate routes).
  - Static files equal the live API on 1,268/1,268 routes.
  - The e2e passes.
- **Codex review:** DISAGREE at first, with one required change. Turning `/api/agencies` into a one-line lambda had changed its OpenAPI `operationId`, which would rename generated client methods. `api.py` was restored to v0.1.0's named handler, and Codex then agreed with no remaining changes.
