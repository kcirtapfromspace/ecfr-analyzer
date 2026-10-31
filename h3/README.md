# H3: Rust and SQLite eCFR analyzer

Run commands from the repository root unless the command changes directory:

```sh
(cd h3 && CARGO_HOME=$PWD/.cargo cargo build --release --offline)
h3/target/release/ecfr ingest --date 2026-10-29 --titles 1,40,41
h3/target/release/ecfr serve --port 8303
```

Omit `--titles` to ingest all non-reserved titles. Downloads require network
access; the supplied three-title cache works entirely offline. The server binds
only `127.0.0.1` and reads `web/index.html` from disk for `/`.

`src/download.rs` manages the shared raw cache, disables automatic gzip decoding,
merges version pages with count assertions, and atomically publishes cache files.
`src/xml.rs` streams gzip XML and retains only the current part's text.
`src/main.rs` builds `data/h3/ecfr.sqlite` transactionally at a temporary path,
then replaces the store. It retains the normalized part metrics, agency membership,
de-duplicated history, and precomputed API JSON. Each request opens its own
read-only connection, so refreshes and concurrent requests do not share a mutable
connection. Agency changes compare checksums against the previous H3 store.

## Verification and measurements

```sh
(cd h3 && CARGO_HOME=$PWD/.cargo cargo fmt --check)
(cd h3 && CARGO_HOME=$PWD/.cargo cargo test --release --offline)
python3 h3/tests/fixtures.py
python3 h3/tests/verify.py
tokei h3/src --files
```

Run the supplied-cache ingest before the HTTP integration test: it copies that
store into a temporary workspace. Handler tests use no sockets and provide their
own temporary HTML fixture. The Python verifier independently computes every part
and API response using stdlib XML, Unicode, regex, and hashing; it also verifies
the original raw-cache hashes. When binding is available, add
`--base http://127.0.0.1:8303` to verify every response over HTTP.

Measured with `/usr/bin/time -p` after the final release build:

- Titles 1, 40, 41: **4.24 seconds wall time** (3.884 seconds inside ingest).
- Store: **6,733,824 bytes** (6.42 MiB); 620 parts and 18,693,857 words.
- All 620 part records and 634 stored responses match the independent oracle.
- Four Rust tests and the ingest fixture suite pass. Tests cover XML text/tails,
  Unicode and headings, all five reference shapes, parent unions, history flags
  and cutoffs, checksum transitions, cache hits, failed-refresh preservation,
  all four API route types, exact unknown-slug 404s, HTML, and concurrent reads.
- `cargo fmt` applied. `tokei h3/src --files`: **704 code lines**:
  `main.rs` 402, `download.rs` 165, `xml.rs` 137.

## Contract interpretations and limits

- The explicit snapshot `--date` controls cache names, XML requests, and history
  filtering even if `titles.json.meta.date` differs. The contract takes precedence
  over the plan's instruction to pin the metadata date.
- Unicode regex word boundaries differ between Python and Rust for combining
  marks and some other word characters. Restrictions use the literal Rust
  `\b(shall|must|may not|required|prohibited)\b` requested by the contract.
  Cached titles 1, 40, and 41 have no observed affected restriction matches;
  their restriction totals match Python exactly.
- Source child agencies omit `children`; those records yield `[]` as required.
  Zero-part agencies remain present on subset ingests. Parts are unique by
  `(title, part)`. These follow the contract over incompatible plan validations.
- Conflicting part values on otherwise duplicate history keys fail the ingest;
  the contract describes that value as shared. Such conflicts are absent here.
- The sandbox rejects localhost binding with `Operation not permitted`.
  Consequently actual HTTP/curl checks could not run; direct handler tests pass.
- The shared `web/index.html` is absent. The disk-reading root handler passes
  with a temporary fixture, but `/` returns a server error until that shared file
  exists. No shared UI was created outside H3.
- Live downloads, uncached titles, and three-implementation parity could not
  run: network access is unavailable and H1, H2, and `bench/parity.py` are absent.
