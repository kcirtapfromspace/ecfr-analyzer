Implemented the SvelteKit candidate. File details are in [README.md](/Users/thinkstudio/usds-ecfr/frontends/sveltekit/README.md).

Created:

- `src/lib/server/fixtures.ts` and index server loader: build-time fixture reads.
- Agency route loader/page: 316 prerender entries, metrics, and history.
- `AgencyScatter.svelte`, `AgencyHistory.svelte`: responsive Chart.js charts.
- `types.ts`, `rows.ts`, `format.ts`: shared types, pure sorting/filtering, number formatting.
- `rows.test.ts`: contract and edge-case tests.
- `app.css`, `atlas.svg`: responsive styling and favicon.
- `node-builtins.d.ts`: narrow Node declarations for the frozen scaffold.

Updated the index, layout, static-generation settings, and Vite configuration.

Validation:

- `BASE_PATH=/ecfr-analyzer npm run build`: **2.42 seconds**, **317 pages**.
- `npm run check`: **0 errors, 0 warnings**.
- `npm test`: **14 passed**.
- Chart.js has its own `chart.DP8FjNFr.js` chunk: **160.75 kB**, **55.62 kB gzip**.
- Verified required hooks, EPA values, all agency pages, 6,021 local references, and no fixture copies. Playwright remains for Claude, per the brief.

SvelteKit 3 surprises were plugin-based configuration, typed route resolution, and enforced chunk naming; a client environment hook preserves Kit’s defaults while naming the chart chunk.

Ambiguities resolved: nulls stay last in both directions; ties preserve source order; searches trim whitespace; initial fixture order has no active header until clicked; named first-agency assertions apply to the top-level directory.