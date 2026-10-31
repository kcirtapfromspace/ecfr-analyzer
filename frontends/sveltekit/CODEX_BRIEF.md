# Brief for Codex: the SvelteKit candidate

We are evaluating four frontends (htmx, raw JS, SvelteKit, Observable Framework) by building the **same slice** of the eCFR UI in each. Read `frontends/CONTRACT.md` first; it is normative. Build the SvelteKit candidate in `frontends/sveltekit/`. A scaffold is already there: SvelteKit 3.1.0, Svelte 5 (runes), adapter-static, Vite 8, TypeScript 6, Vitest 5, chart.js 4.4.1. `node_modules` is installed and the empty scaffold already builds.

## Rules
- **No network** (your sandbox has none), and **no new dependencies**. Everything you need is in `node_modules`. SvelteKit 3 may postdate your training, so read its types and docs in `node_modules/@sveltejs/kit` rather than guessing. Configuration lives in `vite.config.ts` (the `sveltekit({...})` plugin options).
- **Idiomatic SvelteKit static generation:**
  - prerender the index and one page per agency (`/agency/[slug]`, all 316, via `entries`)
  - load data at build time from `../fixtures/api/*.json` (e.g. a `+page.server.ts` reading the files), so the built site ships no fixture copies
  - `adapter-static`, with the base path from the environment (`BASE_PATH`, default `''`); we build with `BASE_PATH=/ecfr-analyzer`
- **Charts:** Chart.js imported from npm and registered tree-shaken (only the controllers, elements and scales you use). If Vite 8's config allows it cheaply, emit chart.js as its own chunk with a name containing `chart` so we can measure it separately. If not, skip that and say so.
- **Testability:** put pure `sortRows` and `filterRows` in `src/lib/` and cover the contract's unit cases with Vitest (`npm test`).
- **Type checks:** `npm run check` (svelte-check) must report 0 errors and 0 warnings.
- Implement every `data-testid`, `data-sort`, `aria-sort` and `data-slug` hook in the contract exactly. A shared Playwright test will run against your build; Claude will run it, since your sandbox can't serve.
- Write readable, idiomatic Svelte 5 + TypeScript. Don't optimize for line count; the comparison includes readability and is scored blindly.

## Run (from `frontends/sveltekit/`)
`BASE_PATH=/ecfr-analyzer npm run build`, `npm run check`, `npm test`. The output goes to `build/`.

## Report (final message, <= 250 words)
- Files you created and their purpose.
- Build time and the number of prerendered pages.
- svelte-check and Vitest results.
- Whether chart.js got its own chunk.
- What was hard or surprising in SvelteKit 3.
- Every contract ambiguity you hit and what you chose.
