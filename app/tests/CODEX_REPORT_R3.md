Created [oracle.py](/app/tests/oracle.py) (**459 lines**) and [expected.json](/app/tests/expected.json), independently from the contract and raw cache.

**Agree with the architecture change:** one Parquet store supports server DuckDB and browser DuckDB-WASM without export drift.

Ambiguities encountered and choices made:

- Filtered candidate metadata: keep `eligible`, `flagged`, and ranks global.
- “Previous kept piece”: rejoin before dropping wordless pieces, following numbered steps.
- Numeric accumulation: use two-pass population variance with `math.fsum`.
- Near-score swaps: use pairwise tolerance, without transitive grouping.
- Flag-cutoff swaps: flags remain exact; the exception explicitly covers ranks.
- Dump schema: use slug-keyed agency metrics, all part metrics, and the full candidate list.

Full-cache run: **219.577 seconds computing; 220.020 seconds total**. Processed all 49 non-reserved titles: **9,659 parts, 6,402 eligible, 641 flagged**.

| Title | Part | Score |
|---:|---:|---:|
| 11 | 108 | 2.246448345810361 |
| 29 | 403 | 2.1035144718043695 |
| 9 | 320 | 2.0922328004671926 |
| 8 | 247 | 1.9987398239702792 |
| 29 | 402 | 1.9593626243467142 |

All **17 offline self-checks passed**, including synthetic-cache integration and comparator edge cases. Dump invariants passed. As instructed, the live `--base` comparison remains for Claude to run.