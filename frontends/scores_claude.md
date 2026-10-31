# Claude's scores (written before reading Codex's), 1–5, higher is better

| Criterion | htmx | raw JS | SvelteKit (lean) | Observable Framework |
|---|---|---|---|---|
| Readability | 3: the logic is split across a Jinja template, `data-v` attributes and DOM JS (two languages for one table) | 4: one explicit flow, but JSDoc casts add noise | 4: declarative markup; you need to know routes, loaders, `$types` and actions | 4: shortest; reactive cells read top-down, though the `Mutable` setter pattern is subtle |
| Ease of change (add a column or a chart) | 3: template header + cell + `data-v` + sort key | 4: header + one row value | 5: header + cell, typed end to end | 4: columns array + cell |
| Testability | 2: data lives in the DOM; unit tests must re-create the template's `data-v` contract | 4: pure module + `node:test`; e2e for DOM | 5: Vitest + svelte-check; components testable | 3: pure module testable; markdown cells aren't |
| Type safety | 1: templates unchecked (a typo is caught only if it reaches a failing filter) | 3: `tsc --checkJs` catches field typos in JS; HTML and chart calls unchecked | 5: template expressions checked; a11y lint too | 1: nothing checked in pages |
