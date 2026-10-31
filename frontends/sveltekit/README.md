# SvelteKit agency explorer

This candidate implements the slice in `../CONTRACT.md` with the installed SvelteKit 3, Svelte 5, and Chart.js dependencies. It needs no network access or additional packages.

Run from this directory:

```sh
BASE_PATH=/ecfr-analyzer npm run build
npm run check
npm test
```

The static site is written to `build/`: the index and 316 agency profiles. Mount the contents at `/ecfr-analyzer/` on a static server. An empty `BASE_PATH` (the default) builds for the domain root. Directory URLs use trailing slashes and `index.html`, so nested profiles work without an SPA fallback.

## Source map

- `src/lib/server/fixtures.ts` reads only the allowed agencies, detail, and history JSON files. Server loaders select just the data each page needs. No fixture files are copied to the output; Kit's generated `__data.json` files support client navigation.
- `src/routes/+page.server.ts` and `+page.svelte` implement the agency directory, search, sorting, and scatter plot.
- `src/routes/agency/[slug]/+page.server.ts` exports all 316 prerender entries. Its sibling page presents agency metrics and history.
- `src/lib/components/AgencyScatter.svelte` and `AgencyHistory.svelte` register the Chart.js controllers, elements, scales, and plugins they use. Browser-only effects create charts and destroy them on navigation or data changes.
- `src/lib/rows.ts` contains pure sort and filter functions; `rows.test.ts` covers the required fixture cases and edge conditions. `types.ts` holds shared data shapes, and `format.ts` centralizes number formatting.
- `src/app.css`, `src/routes/+layout.svelte`, and `src/lib/assets/atlas.svg` provide the responsive layout and visual identity.
- `src/node-builtins.d.ts` declares the small set of Node APIs used here because the frozen scaffold does not include `@types/node`.
- `vite.config.ts` configures adapter-static, the environment base path, and a separate `chart.[hash].js` chunk. A client environment hook preserves Kit's chunk-naming function for other chunks, including its reserved manifest name.

## Contract decisions

- The initial table preserves fixture order (words descending), with no active header until the first click. Thus every numeric header's first click descends, and Agency's first click ascends.
- Missing values stay last in both directions; "nulls rank lowest" could also be interpreted as putting them first in ascending order.
- Equal sort values retain source order. Names compare case-insensitively using the en-US locale.
- Search trims surrounding whitespace; whitespace-only input restores the top-level directory. Nonempty searches include sub-agencies and treat null short names as empty strings.
- The named "first agency" unit expectations apply to the visible top-level directory. Search results still sort across every matching agency.

The shared Playwright test is unchanged and is left for Claude to run, as requested in `CODEX_BRIEF.md`.
