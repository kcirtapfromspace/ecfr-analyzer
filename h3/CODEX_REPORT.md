Implemented H3. Details and commands: [h3/README.md](/h3/README.md).

- **704 code lines**, measured with `tokei` after `cargo fmt`: `main.rs` 402, `download.rs` 165, `xml.rs` 137.
- **Ingest wall time: 4.24 seconds** for titles 1, 40, 41. Store: **6,733,824 bytes** (6.42 MiB).
- Offline release build passes. All **620 parts and 634 stored API responses** match an independent Python calculation. Raw cache hashes remain unchanged.
- Verified all four API route types, unknown-slug 404s, HTML loading, and concurrent reads through direct handler tests. Parser and ingest fixtures pass, including failed-refresh preservation.

Contract choices:
- Explicit `--date` controls the snapshot when metadata dates differ.
- Missing child `children` fields become `[]`.
- Restrictions use Rust’s literal Unicode `\b`; Python boundary differences caused no discrepancies in these cached titles.
- Conflicting part values on duplicate history keys fail ingest.
- Contract overrides conflicting plan requirements: `(title, part)` uniqueness, retention of zero-match agencies, and exact API fields.

Localhost binding was denied, so curl checks could not run. Live downloads and uncached titles remain untested. The shared `web/index.html` is absent; `/` was tested with a temporary fixture and needs that file. H1, H2, and the parity script were unavailable for three-way comparison.