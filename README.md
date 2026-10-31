# eCFR Analyzer

A small site for analyzing the Electronic Code of Federal Regulations (eCFR) to support review of potential deregulation. It shows, per agency:
- word count
- historical changes
- a checksum for change detection
- restriction density, reading grade, staleness, a sentence-type mix and legal authority

It also ranks parts of the CFR as **review candidates** (not findings of over-regulation).

**Live site:** https://kcirtapfromspace.github.io/ecfr-analyzer/ (refreshed daily by GitHub Actions) · **Static JSON API:** [`api/openapi.json`](https://kcirtapfromspace.github.io/ecfr-analyzer/api/openapi.json)

## How it works
- `ecfr ingest`: downloads the eCFR (full XML per title, version history, agencies) into a Parquet store. After the first run it is **incremental**: only titles whose catalog dates moved, or whose stored amendments took effect, are re-downloaded, and only parts whose prose changed are re-analyzed. `--full` reprocesses everything. A daily snapshot per agency and a log of changed parts are kept.
- `ecfr export`: writes a static site. It contains htmx pages, a JSON API mirroring the live routes, and the Parquet files, with text split per title.
- `ecfr serve`: a FastAPI JSON API (`/api/...`, docs at `/docs`) serving the exported site.
- In the browser, every table sorts, search covers sub-agencies, and DuckDB-WASM runs SQL over the published Parquet files.
- `.github/workflows/daily.yml`: runs ingest + export daily (full on Sundays), keeps the store on the `data` branch as one force-pushed commit, and deploys GitHub Pages.
- `.github/workflows/ci.yml`: on every push, lint, the oracle self-tests, the 1,200-line budget, and end-to-end browser tests of the exported site.

**Size:** the app is 1,176 code lines (`tokei app --exclude tests`), and CI fails above 1,200 (`app/tests/loc_gate.py`). Why the UI is htmx, and the other decisions, are in [DECISIONS.md](DECISIONS.md).

## Run locally
```sh
uv sync                # Python 3.12+ and the pinned dependencies from uv.lock
uv run ecfr ingest     # first run: full build, ~4 min plus download
uv run ecfr export     # writes site/
uv run ecfr serve      # http://127.0.0.1:8310 (API docs at /docs)
```

Checks, as CI runs them:
```sh
uv run ruff check app && uv run ruff format --check app/ecfr
uv run python app/tests/loc_gate.py          # needs tokei 15.0.0 (cargo install tokei@15.0.0 --locked)
npm ci && npx playwright install chromium    # once
npm run e2e                                  # tests the exported site/ under /ecfr-analyzer/, as on Pages
```

## Metrics (exact definitions in [CONTRACT.md](CONTRACT.md))
| Metric | Definition |
|---|---|
| Word count | Unicode letter/digit runs in each part's text, summed per agency (sub-agencies included, each part once) |
| Historical changes | Section versions since 2017 from the eCFR versioner, plus this site's own daily snapshots and part-change log |
| Checksum | SHA-256 over each agency's `title|part|text-hash` lines; flags agencies whose text changed |
| Restriction density | "shall / must / may not / required / prohibited" per 1,000 words (RegData term list) |
| Readability | Approximate Flesch–Kincaid grade, words per sentence, long-sentence and passive share (tables excluded) |
| Sentence types | Rule-based classifier: definition, prohibition, paperwork, obligation, permission, other |
| Staleness | Share of current sections with no recorded change since 2017 |
| Authority | What each part's authority note cites; the statutes behind the most text |
| Review candidates | Mean z-score of size, density, grade, directive share, paperwork share, staleness; top 10% flagged |

## Repository map
- `app/ecfr/`: the submission, as a package of composable modules, each usable on its own:

  | Module | Responsibility |
  |---|---|
  | `source.py` | eCFR API client and raw-file cache |
  | `text.py` | Text metrics on strings: words, restriction terms, authority tags, sentences, readability |
  | `parse.py` | Stream a title's XML into one row per part |
  | `build.py` | DuckDB build of the Parquet store: incremental ingest, analytics, ranking, history |
  | `model.py` | Definitions shared by the build and the read layer |
  | `queries.py` | Read queries shared by the API and the export |
  | `site.py` | Static site export; owns `templates/` and `static/` |
  | `api.py` | FastAPI app factory and server |
  | `cli.py` | `ecfr` command |

  `app/tests/oracle.py` is an independent verifier written by Codex from the contract alone; `app/tests/e2e/` tests the exported site in a browser; `app/tests/loc_gate.py` enforces the line budget.
- `DECISIONS.md` (what was chosen, what lost, who agreed, what would reopen it), `CONTRACT.md` (precise spec), `facts.md` (verified eCFR API behavior), `RESULTS.md` (measurements, rounds 1–7), `AGREED_PLAN.md`, `PAGES_PLAN.md`.
- `frontends/`: the round-6 frontend evaluation (htmx, raw JS, SvelteKit, Observable Framework, VanJS, Preact on one shared slice and e2e test). The complete raw-JS port that was measured and set aside is on the `raw-js-port` branch.
- `h1/`, `h2/`, `h3/`, `web/`, `bench/`: measured experiments (Python+SQLite, DuckDB+Parquet, Rust) that led to `app/`.
- `planning/`: the independent Claude and Codex plans and critiques.

## AI use
Built with Claude Code (Claude) and Codex working as two agents. They wrote independent plans and critiqued each other's. Claude wrote the Python app; Codex wrote the Rust experiment and the independent oracle. Every round was verified by measurement: parity across implementations, oracle checks, incremental-vs-full equality, and browser tests. Disagreements and the user's calls are recorded in `DECISIONS.md`. `RESULTS.md` records who did what and every bug found.
