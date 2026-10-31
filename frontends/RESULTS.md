# Round 6: frontend evaluation (htmx vs raw JS vs SvelteKit vs Observable Framework)

**Method:** each candidate implements the same slice (`CONTRACT.md`) from the same fixture JSON:
- the agency table, with sort (▲/▼, reversing) and search that includes sub-agencies
- the words × density scatter plot
- an agency detail view with a stacked history chart

All five builds pass one shared Playwright test (`e2e/slice.spec.js`) under the `/ecfr-analyzer/` subpath with a Range-capable static server, as on GitHub Pages. So they are equivalent before they are compared.

Observable Framework was chosen as the 4th candidate over Astro because it is a static generator built for data apps (build-time data loaders, Plot, DuckDB-WASM). Packages were pinned to versions at least 2 weeks old: SvelteKit 3.1.0, Svelte 5.57.2, Vite 8.3.4, TypeScript 6.0.3, Vitest 5.0.5, Framework 1.13.4, Chart.js 4.4.1, Playwright 1.64.1.

| | htmx (Jinja pre-render) | raw JS (no build) | SvelteKit lean | SvelteKit (Codex, polished) | Observable Framework |
|---|---|---|---|---|---|
| Static generation | Python/Jinja writes index + 316 fragments | none; the page fetches JSON | prerenders index + 316 pages; data inlined | same | build-time data loaders (Python) → 1 page |
| Code lines (non-blank, non-comment) | 160 | 156 | 220 | 1,118 (465 CSS, extra copy/a11y text) | 89 |
| Config lines | 26 | 24 | 91 (≈35 are a chunk-naming plugin used only for measurement) | 90 | 36 |
| Unit-test lines (5 contract cases) | 30 | 27 | 27 | 100 (14 cases) | 27 |
| **First view, gzip** | 119.5 KB / 6 req | 135.6 KB / 7 req | **114.8 KB** / 15 req | 120.3 KB / 17 req | 394.8 KB / 48 req |
| …chart library | 67.9 KB (Chart.js UMD) | 67.9 KB | 53.6 KB (tree-shaken) | 53.6 KB | 180.9 KB (Plot + d3, 36 req) |
| …framework runtime | 16.0 KB (htmx) | 0 | 34.7 KB (framework + page code; Vite bundles them together) | 34.3 KB (same) | 25.3 KB |
| …data / page | 33.9 KB HTML with rows | 63.6 KB full `agencies.json` | 24.6 KB HTML incl. trimmed data | 28.0 KB | 63.6 KB + **120 KB Google Fonts** (default theme) |
| Detail view, gzip | 0.4 KB | 1.6 KB | 1.0 KB | 3.1 KB | 11.8 KB (all histories, once) |
| Build / type check / unit tests | 0.3 s / 0.5 s / 0.3 s | — / 0.5 s / 0.3 s | 2.3 s / 3.7 s / 1.3 s | 2.4 s / 2.0 s / 1.0 s | 1.5 s (network on first build) / 0.4 s / 0.3 s |
| Dev dependencies | Python `jinja2` (already used) | none (shared `tsc` optional) | 59 pkgs, 90 MB, Node in CI | same | 216 pkgs, 81 MB, Node + network in CI |
| Deploy size | 320 files, 1.4 MB | 638 files, 2.8 MB (fixtures) | 651 files, 2.9 MB | 655 files, 4.2 MB | 47 files, 1.1 MB |
| **Planted field typo** (`stale_shar`) | not by `tsc`; build fails only because a filter did arithmetic (bare `{{ }}` would render blank) | **caught by `tsc --checkJs`** | **caught by svelte-check in the template** | caught | **not caught** (check, build and page all pass; shows "—") |
| Keyboard-accessible sort and rows | no (clickable `th`/`tr`) | no | **yes** (buttons + links, enforced by svelte-check a11y) | yes | no |

**Readability (1–5; Claude | Codex).** Codex scored blind to Claude's scores and did not score its own polished version.

| | Readability | Ease of change | Testability | Type safety |
|---|---|---|---|---|
| htmx | 3 \| 4 | 3 \| 3 | 2 \| 3 | 1 \| 2 |
| raw JS | 4 \| 4 | 4 \| 4 | 4 \| 4 | 3 \| 3 |
| SvelteKit lean | 4 \| 4 | 5 \| 4 | 5 \| 4 | 5 \| 4 |
| Observable | 4 \| 4 | 4 \| 4 | 3 \| 3 | 1 \| 2 |

## What the build-out taught (real pitfalls hit)
- **SvelteKit 3** moved its config into the Vite plugin and writes the TypeScript config into `node_modules/$app`, so two projects sharing `node_modules` break each other's types.
- Svelte's checker flagged a reactivity hazard (`state_referenced_locally`; harmless for prerendered data that never changes) and pushed toward accessible buttons and links. A sort button smaller than its header cell left a dead click zone; the shared e2e caught it.
- **Observable Framework**'s default theme pulls 120 KB of Google Fonts from Google (a privacy and payload cost, fixable in config). Plot pulls ~36 small d3 modules. Page JavaScript in Markdown is not type-checked.
- **htmx**: the table's data lives in DOM attributes, so unit tests must re-create the template's `data-v` contract, and logic is split across Python, Jinja and JS.
- **raw JS**: the cheapest toolchain. Because rendering is JS, JSDoc + `tsc --checkJs` covers the rendering code too. It ships the full 276 KB `agencies.json`; a trimmed table JSON would cut ~50 KB gzip.

## Recommendation
- **SvelteKit, written lean** (actions for charts, one CSS file, prerendered pages) is the best fit for **tests and type checks**, which is what you asked to optimize. It has the lightest first view (115 KB), tree-shaken Chart.js, template-level type and accessibility checks, and Vitest. Codex independently chose it.
  - Its costs are real: about 1.4–1.7× the frontend lines of htmx/raw for the same scope, and a Node toolchain (59 dev packages) in CI.
  - Fix its main risk (Codex): loaders cast exported JSON to TypeScript types without checking them. Generate TS types from the Python side (the app already writes `api/openapi.json`; add schemas, then `openapi-typescript`), or validate the shape in the loaders.
- **raw JS + JSDoc** is the budget pick: the same lines as htmx, no build, no runtime framework, and field typos in rendering code still caught by `tsc`.
- **Observable Framework** has the nicest chart code and data loaders, but is 3.4× heavier and has no type checks in pages. Use it for exploratory dashboards, not here.
- **htmx** stays the cheapest to keep (0 port cost) but is weakest on tests and types.
- **Line budget** (estimate from slice ratios, not measured):
  - Porting the current UI (≈350 frontend lines) to SvelteKit lean ≈ 550–600 lines, so the app grows to ≈1,400 + config. That is over 1,200 unless something else shrinks.
  - Raw JS ≈ 400 lines, so the app stays ≈1,230.

## Addendum: is anything better than raw JS under the 1,200-line cap?
Two more no-build candidates were built against the same contract and harness (import maps + SRI; they reuse raw's `table.js`, `charts.js` and unit tests). Both pass the shared e2e.

| | raw JS | VanJS 1.6.1 | Preact 11 + htm 3.1.1 |
|---|---|---|---|
| Lines (Prettier, width 100; JS + HTML + CSS) | **186** | 217 | 220 |
| First view, gzip | **135.6 KB** | 137.3 KB | 143.3 KB |
| Planted typo caught by `tsc` | yes | yes (template calls are JS) | yes (`${}` expressions are JS) |
| Snags hit | none | chart lifecycle: each detail re-render leaves the old Chart.js instance undestroyed (Codex) | the import map needed the transitive `htm` entry |

**Verdict (Claude and Codex agree):** no. Raw JS stays the pick for this cap. VanJS is the runner-up if the UI grows, and only after adding chart cleanup.

The bigger levers aren't the framework:
- trim the table JSON (~50 KB gzip)
- possibly swap the chart library: uPlot is 21.5 KB gzip vs Chart.js at 67.9 KB, but it is lower-level, so "rich graphs" cost more code

## The full port, measured (round 7)
The slice-based estimate for raw JS was ≈1,230 app lines. The complete, feature-equivalent port (branch `raw-js-port`) measured **1,228**, 28 over the 1,200 preference. It does use the trimmed table JSON: first view 102.5 KB gzip vs 126.5 KB for htmx, and agency detail 6.3 KB vs 3.1 KB. Under the agreed rule ("if it cannot fit, keep htmx"), the user kept htmx. See `../DECISIONS.md` (D7).
