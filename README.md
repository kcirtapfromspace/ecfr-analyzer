# eCFR Analyzer

This website helps you find federal regulations to examine for deregulation. It uses the full Electronic Code of Federal Regulations (eCFR) and updates each day.

- **Live site:** https://kcirtapfromspace.github.io/ecfr-analyzer/
- **JSON API:** [api/openapi.json](https://kcirtapfromspace.github.io/ecfr-analyzer/api/openapi.json)

## What it shows

Each agency value includes its sub-agencies and counts each part one time.

| Metric | Definition |
|---|---|
| Word count | The words in the agency's parts of the CFR |
| Historical changes | Section changes per year from 2017 (eCFR versioner), plus a daily snapshot from this site |
| Checksum | A SHA-256 hash of the agency's text. A new value shows that the text changed. |
| Restriction density | Restriction terms ("shall", "must", "may not", "required", "prohibited") per 1,000 words |
| Reading grade | Approximate Flesch–Kincaid grade, words per sentence, share of long and passive sentences |
| Sentence types | Rule-based classifier: definition, prohibition, paperwork, obligation, permission, other |
| Staleness | The share of sections with no change from 2017 |
| Authority | The statutes that the parts cite, and the quantity of text for each statute |

The site also gives each part of the CFR a **review candidate** score. The score is the mean z-score of size, restriction density, reading grade, directive share, paperwork share and staleness. The top 10% get a flag for review. A flag is not a conclusion about the part.

## How it works

- `ecfr ingest` downloads the eCFR XML, the version history and the agencies into Parquet files. After the first run, it processes only the titles that changed.
- `ecfr export` writes the static site: htmx pages, the JSON API as files, and the Parquet data.
- `ecfr serve` gives the same API from a FastAPI server (documentation at `/docs`).
- In the browser, you can sort tables, search agencies and query the Parquet files with SQL (DuckDB-WASM).
- Each day, GitHub Actions updates the data and publishes the site to GitHub Pages. The data stays on the `data` branch.

## Run it

```sh
uv sync              # Python 3.12 and the pinned packages
uv run ecfr ingest   # first run: a full build, approximately 4 minutes plus the download
uv run ecfr export   # writes site/
uv run ecfr serve    # http://127.0.0.1:8310
```

CI runs these checks for each push:

```sh
uv run ruff check app
uv run python app/tests/loc_gate.py        # needs tokei 15.0.0
npm ci && npx playwright install chromium  # one time
npm run e2e                                # browser tests of site/ under /ecfr-analyzer/
```

## Decisions

- **DuckDB and Parquet.** We measured three backends: Python with SQLite, Python with DuckDB and Parquet, and Rust. The Rust ingest was 2.4 times faster, but this data does not need that speed. With Parquet, the server and the browser query the same files.
- **Static site.** GitHub Pages hosts the pages and the API as files, so there is no server to operate.
- **Rule-based sentence types.** Jev is a closed, hosted API that we cannot embed. Rules are easy to explain.
- **htmx.** SvelteKit was the first choice for its type checks and tests. But with SvelteKit, the app needs approximately 1,400 lines (an estimate). With a plain JavaScript port, it needs 1,228 lines (branch `raw-js-port`). With htmx, the app stays below 1,200 lines.
- **Size.** The app has 1,176 lines of code (`tokei app --exclude tests`). CI fails above 1,200.
- **Open item.** The paperwork share controls the top of the list. A ±3 limit on each z-score can correct this. This is not decided.

## How we checked the results

- Codex wrote an independent oracle from the specification. It calculated all 9,659 parts again and found 0 differences from the API.
- The static API is the same as the live API on all 1,268 routes.
- An incremental build gives the same result as a full build (float differences below 5e-11).
- Browser tests in CI sort, search and open agency details. They get their expected values from the site's JSON.

## AI use

- Claude (Claude Code) and Codex worked as two agents. Each agent wrote a plan and examined the plan of the other agent.
- Claude wrote the app. Codex wrote a Rust version for comparison, the oracle, and a review of each step.
- We measured each claim before we accepted it. The author made the final decisions.

## Limits

- The reading grade and the sentence splits are approximate.
- Version history before 2017 is the eCFR baseline load. Thus, the site counts changes from 2017-01-01.
- The site gives each change to the agency that owns the part now.

The tag [v0.2.0](https://github.com/kcirtapfromspace/ecfr-analyzer/tree/v0.2.0) has the earlier experiments, measurements and full decision record.
