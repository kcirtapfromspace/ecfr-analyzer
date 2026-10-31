# Plan: publish `app/` as a static site on GitHub Pages: BUILT in round 4 (see RESULTS.md); repo/push pending

Verified 2026-10-30: GitHub Pages answers Range requests with HTTP 206 and sends `Access-Control-Allow-Origin: *`; published sites max 1 GB; deploys time out at 10 minutes.

## What changes
| Dynamic app (today) | Static site |
|---|---|
| FastAPI routes | `uv run ecfr export` writes files, using the same query functions |
| `/api/agencies/{slug}` etc. | `api/agencies/{slug}.json` etc., plus `api/openapi.json` describing the real `.json` paths |
| `?agency=…&limit=…` | path params: `api/candidates/{slug}.json`, fixed limit (500) |
| `{"detail":"not found"}` 404 | GitHub's own 404 HTML page (document it in the static contract) |
| htmx → server fragments | htmx → pre-rendered `ui/agency/{slug}.html`, `ui/candidates/{slug or all}.html`,  |
| server search (`q`) | client-side filter over **all** pre-rendered agency rows, sub-agencies included; re-applied after each sort swap |
| absolute URLs | relative URLs (project sites live under `/<repo>/`) |
| ingest on demand | scheduled GitHub Actions job: ingest (~4 min, 2.3 GB), download the previously published `agencies.parquet` (keeps "changed since last publish"), export, upload-pages-artifact, deploy-pages |
| `parts_text.parquet` 140 MB | shard per title, or omit (the UI never needs it) |

## Meeting "store data server-side, create APIs that retrieve it"
1. **Static read-only REST API:** GET JSON resources with an OpenAPI file, refreshed by a scheduled server-side job (Actions).
2. **Data over HTTP:** the published Parquet files can be queried by URL from any DuckDB (WASM in the page, or the CLI/Python). The SQL runs on the client, not the server.
3. **The dynamic FastAPI server stays in the repo** and is the live demo (`/docs`). It is the strongest evidence for the criterion. A parity script checks that every static JSON file parses equal to the matching live response.

## Costs and caveats
- Code lines +70-100, so ~1,010-1,040 including the workflow YAML (under 1,200).
- Pages on a **private** repo needs a paid GitHub plan, and the site is public anyway, so the USDS-provided private repo may not be able to host it. Use a separate public repo.
- Lost: arbitrary query params, server-side search, real-time freshness (refresh is daily).
