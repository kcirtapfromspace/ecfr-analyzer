A. Concrete problems in Claude’s plan, most important first:

1. **History is silently incomplete.** One versions request retrieves only 1,000 rows; Title 40 needs 61 pages. Follow pagination metadata and verify retrieved totals. The 5–10-minute ingestion estimate needs remeasurement.
2. **Baseline loads become fake changes.** Round 1 counts initialization rows as activity. However, excluding every section’s first version also discards later first appearances, so that correction changes the metric’s meaning.
3. **Refresh safety is unspecified.** Updating the live database risks mixed or incomplete results after failure. P2’s validated replacement database fixes this.
4. **History’s contract is incomplete.** Current part ancestry cannot prove historical ownership; removed parts may be unmatched. Preserve `type` in event identity, filter through the snapshot date, define deduplication/removal handling, and retain `amendment_date` if displaying “last amended.”
5. **PART scope omits potentially attributable text.** Zero orphan sections does not establish zero chapter headings, appendices, or other text outside parts. Define the count as *text within PARTs*, report excluded words, and validate uniqueness/containment nationwide.
6. **Sorted bare hashes lose identity.** Moving text between parts, or replacing a part with another identifier containing identical text, can leave the agency checksum unchanged. Hash identifiers alongside text hashes.
7. **Restriction density overclaims.** Term matches do not establish binding obligations or identify the “most burdensome” rules. Present this as a lexical signal for review prioritization.
8. **Streaming cleanup needs an explicit rule.** Clearing descendants before collecting their PART’s text destroys the content being measured. Accumulate text before clearing, or retain descendants until PART completion.

B. Responses to P1–P8:

- **P1 — AGREE.** PART storage plus `agency_part` wins on simplicity, provided nationwide assertions pass and the UI explicitly reports the narrower text scope and exclusions.
- **P2 — AGREE.** A validated replacement database preserves the previous import without snapshot IDs everywhere; close/checkpoint it before replacement.
- **P3 — AGREE.** Stdlib `iterparse` has measured performance and is easier to explain; implement clearing correctly.
- **P4 — DISAGREE.** Pagination and baseline suppression are necessary, but first-version exclusion also removes later first appearances. Compromise: use that simple rule only with the label **“revisions after first observation,”** explicitly stating that additions are excluded.
- **P5 — AGREE.** Yearly bars are sufficient for this budget; label them recorded revisions, because revision counts do not demonstrate regulatory growth.
- **P6 — AGREE.** Static HTML plus FastAPI’s generated API documentation is a reasonable screen-share advantage; Flask/Jinja is not worth defending here.
- **P7 — AGREE.** Boundary-aware “may not” matching costs little and improves the term list; retain the lexical-proxy caveat rather than claiming measured burden.
- **P8 — AGREE.** Hosting is optional after correctness, screenshots, and documentation are complete; a Dockerfile alone does not establish a working deployment.

C. Round-1 choices Claude should still adopt, beyond A1–A5 already accepted:

- **Identity-bearing checksum inputs:** simplify my node records to ordered `(title, part, text_hash)` records. This preserves attribution identity with little code.
- **Explicit current-ownership and unmatched-history reporting:** reviewers need to see where historical attribution is approximate or unavailable.
- **Measured ingestion with caching, retries, and checkpoints:** pagination makes resumability more valuable than an optimistic download estimate.
- **The required skills-fit explanation:** Claude’s submission checklist omits it; my checklist includes it.

I would drop my SAX parser, all-DIV schema, multi-snapshot tables, monthly chart default, and inclusion of initialization rows as meaningful activity.