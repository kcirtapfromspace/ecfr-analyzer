1. **Stack**
   - **Python:** standard-library XML parsing, hashing, and SQLite keep the implementation explainable.
   - **Flask:** small routing layer with little framework machinery.
   - **SQLite + cached source files:** persistent server-side storage without infrastructure.
   - **Jinja, vanilla JavaScript, Chart.js:** one page, conventional charts, no frontend build pipeline; vendor Chart.js locally.

2. **Ingest strategy**
   - Fetch agencies/titles; pin `meta.date` and reject imports while `import_in_progress`. Download nonreserved titles’ full XML and versions JSON. Never use chapter filters or unverified daily-count semantics.
   - Use two workers, compression-enabled requests, timeouts/retries, cached files, and per-title checkpoints.
   - Stream XML through a SAX parser: retain hierarchy and metric accumulators; buffer at most one text block. Archive compressed XML and original JSON.
   - Allow 15–30 minutes for downloads **as an assumption to measure immediately**.
   - Manual CLI refresh builds a new snapshot; publish only after validation. Failed refreshes preserve the previous snapshot.

3. **Agency attribution**
   - Match every supplied reference field conjunctively against XML ancestry. Map `subchapter` to `SUBCHAP`; preserve identifiers as strings, including `"0"`.
   - Partition XML into each DIV’s own text, excluding nested DIV text. Matching a reference selects all these disjoint units in its subtree.
   - Agency totals union unit IDs across references. Parent totals union their own references with every descendant agency’s references; never sum children’s totals.
   - Separate agencies can legitimately overlap; their totals are not additive.
   - Build `(title, part) → ancestry` during parsing for history attribution.

4. **Exact metric definitions**
   - **Word count:** number of Unicode alphanumeric runs, matching `[^\W_]+`, in matched XML text. Include headings, tables, and appendices; exclude attributes/comments. Apostrophes and hyphens split words. Count every text unit once.
   - **Historical changes:** monthly count of distinct version events keyed by `(title, part, type, identifier, date)`, through the snapshot date. Include initial versions and removals; label the chart “Recorded version events.” Attribute using current part ancestry; report unmatched events separately. This is not historical word count or proven historical ownership.
   - **Checksum:** SHA-256 of canonical JSON records containing title, node path, and normalized text digest, ordered by numeric title and document position. Normalize Unicode to NFC and collapse whitespace; preserve case and punctuation.
   - **Custom metric:** restriction-term density = `1,000 × occurrences of {must, shall, required, prohibited} / words`, using case-insensitive exact tokens; null for zero words. Helps prioritize review of directive-heavy text, without claiming to measure actual regulatory burden.

5. **Storage schema**
   - `snapshots(id, data_date, status, created_at)`
   - `titles(snapshot_id, number, status, xml_path, versions_path, error)`
   - `agencies(snapshot_id, slug, parent_slug, name, refs_json, words, restriction_hits, checksum)`
   - `nodes(id, snapshot_id, title, path, parent_path, kind, identifier, ordinal, subtitle, chapter, subchapter, part, words, restriction_hits, text_sha)`
   - `agency_nodes(agency_slug, node_id)` — unique membership, including parent rollups.
   - `versions(snapshot_id, title, part, type, identifier, date, substantive, removed)` — unique event key.

6. **API routes**
   - `GET /api/agencies` → `{snapshot, agencies:[{slug,parent_slug,name,words,restriction_density,checksum}]}`
   - `GET /api/agencies/<slug>` → `{summary,references,children,coverage}`
   - `GET /api/agencies/<slug>/history` → `{basis:"current ownership",months:[{month,events}],unmatched_title_events}`
   - `GET /api/status` → `{data_date,last_success,titles_complete,titles_expected,validation}`
   - Imports remain a CLI operation.

7. **UI**
   - One dashboard: searchable, sortable agency table; expand children; select an agency for details.
   - Detail panel: word count, restriction density, copyable checksum, monthly history, references, and attribution caveat.
   - Chart.js horizontal comparison bars and history line; accessible tables provide the same values. Display snapshot date and coverage prominently.

8. **LOC budget**
   - Import/parser: **300**; attribution/metrics: **170**; schema/API: **170**; HTML/CSS/JavaScript: **300**; CLI/configuration: **60**; reserve: **150**. **Total: 1,150**, excluding tests and generated/vendor files.
   - Four hours: ingest **90 min**, backend **40**, UI **60**, tests/documentation **50**. Avoid deployment infrastructure and scheduled refreshes.

9. **Tests worth writing**
   - Fixture covering all five reference shapes, chapter `"0"`, overlapping references, and parent/child unions.
   - Nested XML text counted once; arbitrary streaming boundaries produce identical metrics.
   - Checksum ignores whitespace changes but detects punctuation changes.
   - History deduplication, removed events, and unmatched parts.

10. **Top 3 risks and mitigations**
   - **Unverified nationwide behavior:** validate part uniqueness, ancestry, reference resolution, reserved-title handling, and version payload sizes. Block incomplete publication; expose diagnostics.
   - **Historical misattribution:** current structure cannot establish past ownership. Label the approximation and retain unmatched events.
   - **Time/LOC overrun:** start nationwide ingestion immediately; measure throughput. Keep one dashboard, manual refresh, and one custom metric.

11. **Submission document + AI collaboration**
   - Include actual skills fit, measured time, setup/refresh commands, metric definitions, limitations, screenshots, and frontend link if hosted.
   - Describe Claude’s and Codex’s independent plans, disagreements, and merged decisions honestly. Identify generated versus author-written work, verification performed, and the author’s responsibility for explaining every submitted component.