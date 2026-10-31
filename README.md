# eCFR Analyzer

A small site for analyzing the Electronic Code of Federal Regulations (eCFR) to support review of potential deregulation. It shows, per agency:
- word count
- historical changes
- a checksum for change detection
- restriction density, reading grade, staleness, a sentence-type mix and legal authority

It also ranks parts of the CFR as **review candidates** (not findings of over-regulation).

**Live site:** https://kcirtapfromspace.github.io/ecfr-analyzer/ (refreshed daily by GitHub Actions) · **Static JSON API:** [`api/openapi.json`](https://kcirtapfromspace.github.io/ecfr-analyzer/api/openapi.json)

## How it works
- `app/ecfr.py ingest`: downloads the eCFR (full XML per title, version history, agencies) into a Parquet store. After the first run it is **incremental**: only titles whose catalog dates moved, or whose stored amendments took effect, are re-downloaded, and only parts whose prose changed are re-analyzed. `--full` reprocesses everything. A daily snapshot per agency and a log of changed parts are kept.
- `app/ecfr.py export`: writes a static site. It contains htmx pages, a JSON API mirroring the live routes, and the Parquet files, with text split per title.
- `app/ecfr.py serve`: a FastAPI JSON API (`/api/...`, docs at `/docs`) serving the exported site.
- In the browser, every table sorts, search covers sub-agencies, and DuckDB-WASM runs SQL over the published Parquet files.
- `.github/workflows/daily.yml`: runs ingest + export daily (full on Sundays), keeps the store on the `data` branch as one force-pushed commit, and deploys GitHub Pages.

## Run locally
```sh
python3 -m venv .venv && .venv/bin/pip install -r app/requirements.txt
.venv/bin/python app/ecfr.py ingest      # first run: full build, ~4 min plus download
.venv/bin/python app/ecfr.py export      # writes site/
.venv/bin/python app/ecfr.py serve       # http://127.0.0.1:8310 (API docs at /docs)
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
- `app/`: the submission (1,151 code lines; workflow 49; total 1,200). `app/tests/oracle.py` is an independent verifier written by Codex from the contract alone.
- `CONTRACT.md` (precise spec), `facts.md` (verified eCFR API behavior), `RESULTS.md` (measurements and decisions, rounds 1–4), `AGREED_PLAN.md`, `PAGES_PLAN.md`.
- `h1/`, `h2/`, `h3/`, `web/`, `bench/`: measured experiments (Python+SQLite, DuckDB+Parquet, Rust) that led to `app/`.
- `planning/`: the independent Claude and Codex plans and critiques.

## AI use
Built with Claude Code (Claude) and Codex working as two agents. They wrote independent plans and critiqued each other's. Claude wrote the Python app; Codex wrote the Rust experiment and the independent oracle. Every round was verified by measurement: parity across implementations, oracle checks, incremental-vs-full equality, and browser tests. `RESULTS.md` records who did what and every bug found.
