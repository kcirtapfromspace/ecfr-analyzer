Implemented all Round 2 additions and the independent oracle, entirely offline.

- **Code:** 822/900 lines after formatting: `main.rs` 452, `xml.rs` 206, `download.rs` 164.
- **Nationwide ingest:** 24.76 seconds wall time.
- **Oracle:** 9,659 parts and 634 stored API responses verified; **zero mismatches**.
- **Validation:** release build, all six Rust tests, expanded fixtures, and formatting check passed.
- **Contract ambiguities:** none found.

The `facts.md` count includes 24 current rows with null parts. Excluding them as the contract requires gives **231,300 current sections**, including **135,542 stale sections**.