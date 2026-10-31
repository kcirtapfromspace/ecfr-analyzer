# Decisions

A dated record of the choices that shaped this repo: what was chosen, what lost and why, who agreed, and what would reopen each one. The measurements are in [RESULTS.md](RESULTS.md) and [frontends/RESULTS.md](frontends/RESULTS.md).

## D7. Frontend: keep htmx; SvelteKit was the first choice, a raw-JS port was built and set aside (2026-10-30, Checkpoint 2)

**Decision:** the UI stays htmx + Jinja, pre-rendered by `ecfr export`, exactly as in Checkpoint 1.

**How we got there:**
1. **SvelteKit was the user's first choice**, for its type checks. In the evaluation (round 6) it won what was asked for: template-level type and accessibility checks (`svelte-check`), Vitest, and the lightest first view of the five candidates (114.8 KB gzip). Codex independently chose it too.
2. **The 1,200-line preference ruled it out.** The slice cost about 1.4× htmx's lines for the same scope, so the full UI would bring the app to about 1,400 lines plus a Node toolchain (an estimate from the slice ratio; the full SvelteKit port was not built). That is over the budget unless requested features are removed.
3. **Raw JS + JSDoc was the budget pick.** It had htmx's line count on the slice, no build step, and `tsc --checkJs` caught the planted field typo. VanJS and Preact were built as well and were no better under the cap. Claude and Codex agreed, with **Codex's condition: "measure the complete, feature-equivalent port and enforce ≤1,200 lines in CI ... If it cannot fit, keep htmx."**
4. **The complete port was built and measured** (branch [`raw-js-port`](https://github.com/kcirtapfromspace/ecfr-analyzer/tree/raw-js-port)). It is feature-equivalent, passes `tsc` and the shared slice e2e, and was checked in a browser. tokei first reported 1,261 lines, but 32 of those were comment lines it miscounted as code because of a quote inside a regex literal. Rewriting that regex gave 1,230. Removing duplicated SQL in `build.py`, net of two small fixes in the port, gave 1,228: **28 over 1,200**.
5. **The user chose to keep htmx and stay under 1,200** over shipping the port at 1,228 or cutting a feature to fit.

**What the port would have bought** (same store, same measurement):

| | htmx (shipped) | raw JS port |
|---|---|---|
| App code lines (tokei) | **1,176** | 1,228 |
| First view, gzip | 126.5 KB / 5 requests | 102.5 KB / 13 requests |
| Agency detail, gzip | 3.1 KB | 6.3 KB |
| Type-checked rendering | no (Jinja templates unchecked) | yes (`tsc --checkJs`) |

**What we kept from the attempt:**
- The LOC gate in CI (`app/tests/loc_gate.py`).
- An end-to-end test of the shipped htmx UI (`app/tests/e2e/`), which fails if header sorting breaks.
- Duplicated SQL removed from `build.py`, with the generated SQL verified byte-identical to v0.1.0's.

**What would reopen it:**
- The line budget is lifted or relaxed (SvelteKit lean is then the pick, with types generated from `api/openapi.json`).
- The UI grows enough that untyped templates become the main source of bugs.
- The trimmed-JSON port (102.5 KB first view) becomes worth 28 lines.

## Earlier decisions (rounds 1–5, all on 2026-10-29/30)

| # | Round | Decision | Why | Agreed by | What would reopen it |
|---|---|---|---|---|---|
| D1 | 1 | Python, not Rust. H3 (Rust) fit in 920 lines and ingested 2.4× faster | Reviewers won't see the speed at this data size; Python is easier to walk through on a screen-share | Claude and Codex | A need for a tiny server or much faster ingest |
| D2 | 3 | One DuckDB + Parquet store (H2), replacing H1's SQLite | "One Parquet store supports server DuckDB and browser DuckDB-WASM without export drift" (Codex); the user asked to try DuckDB + Parquet | Claude and Codex | Runner memory limits (the build caps DuckDB at 1 GB and spills to disk) |
| D3 | 3 | A rule-based sentence classifier and approximate readability instead of Jev | Jev is a closed, hosted, early-access API that can't be embedded; rules are transparent and explainable | Claude and Codex (round-3 sign-off) | A labeled sample showing the rules misclassify too often |
| D4 | 3 | Review candidates = mean z-score of six equal-weight inputs, top 10% flagged | Simple, and every input is visible per part. The long-tailed paperwork share dominates the top; capping each z at ±3 is **still open, as the user's choice** | Claude and Codex | Deciding on the ±3 cap |
| D5 | 4 | A static GitHub Pages site plus an incremental daily refresh on Actions; the store lives on a force-pushed `data` branch | No server to run; history lives in Parquet (`agency_history`, `part_changes`), not in git commits | Claude. Codex reviewed it, required four fixes and changed the incremental design; all were applied | A need for live queries the static API can't answer |
| D6 | 5 | uv for all Python; the app split into composable modules | The user's requests; one lockfile for local runs and CI | The user; Codex reviewed the split and agreed | — |

## Line counting (applies to every number here)
- `tokei app --exclude tests` (tokei 15.0.0) counts code lines only: no blanks, comments, tests or generated files. Python is formatted with `ruff format --line-length 100`, pinned in `pyproject.toml`.
- CI enforces the 1,200-line budget with `app/tests/loc_gate.py`.
- tokei doesn't parse regex literals. `app/ecfr/static/app.js` has a quote inside one, so tokei counts 3 of its comment lines as code (120 by a plain count). We report tokei's higher number.
- Workflows and `pyproject.toml` are not counted, as in round 5.
