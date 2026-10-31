// The agency detail panel: metrics, top review candidates, size and change charts, statutes and largest parts.
import { destroyCharts, historyChart, trendChart } from "./charts.js";
import { agencyHref, candidateColumns, candidatesNote } from "./columns.js";
import { f1, getJSON, html, num, pct, sortable } from "./ui.js";

/**
 * GET api/agencies/{slug}.json (fields in CONTRACT.md); only what this panel reads.
 * @typedef {{name: string, words: number, parts: number, restrictions: number, density: number | null,
 *   readability: {sentences: number, fk_grade: number | null, words_per_sentence: number | null, long_share: number | null,
 *     passive_share: number | null, crossrefs_per_1k: number | null},
 *   sentence_types: Record<string, number>, sections: number, stale_sections: number, stale_share: number | null,
 *   flagged_parts: number, last_changed: string | null, checksum: string | null, changed: boolean, children: string[],
 *   top_statutes: {cite: string, words: number, parts: number}[],
 *   top_parts: {title: number, part: string, heading: string, words: number}[]}} Agency
 */

let latest = "";

/** Fetch and draw one agency; a slower earlier request never overwrites a newer pick. @param {HTMLElement} panel @param {string} slug */
export async function showAgency(panel, slug) {
  latest = slug;
  const base = `api/agencies/${encodeURIComponent(slug)}`;
  let data;
  try {
    data = await Promise.all([getJSON(`${base}.json`), getJSON(`${base}/history.json`), getJSON(`${base}/trend.json`),
      getJSON(`ui/candidates/${encodeURIComponent(slug)}.json`)]);
  } catch (err) {
    if (slug !== latest) return;
    destroyCharts(panel);
    panel.innerHTML = html`<p class="sub">Could not load agency ${slug}: ${/** @type {Error} */ (err).message}</p>`.text;
    return;
  }
  if (slug !== latest) return;
  const [a, history, trend, candidates] = /** @type {[Agency, {years: import("./charts.js").Year[]},
    {days: import("./charts.js").Day[]}, import("./columns.js").Candidates]} */ (data);
  const r = a.readability;
  const types = Object.entries(a.sentence_types).filter(([, n]) => n).map(([t, n]) => `${t} ${pct(n / r.sentences)}`);
  destroyCharts(panel);
  panel.innerHTML = html`<h2 data-testid="detail-name">${a.name}</h2>
<dl class="kv">
  <dt>Words</dt><dd><span data-testid="detail-words">${num(a.words)}</span> in ${num(a.parts)} parts</dd>
  <dt>Restriction terms</dt><dd>${num(a.restrictions)} (<span data-testid="detail-density">${f1(a.density)}</span> per 1,000 words)</dd>
  <dt>Reading grade</dt>
  <dd>${f1(r.fk_grade)} (Flesch–Kincaid, approximate) · ${f1(r.words_per_sentence)} words per sentence ·
    ${pct(r.long_share)} of sentences over 40 words · ${pct(r.passive_share)} passive ·
    ${f1(r.crossrefs_per_1k)} cross-references per 1,000 words</dd>
  <dt>Sentence types</dt><dd>${types.join(" · ")}</dd>
  <dt>Unchanged since 2017</dt><dd>${num(a.stale_sections)} of ${num(a.sections)} sections (${pct(a.stale_share)})</dd>
  <dt>Flagged parts</dt><dd>${num(a.flagged_parts)} in the top 10% of review candidates</dd>
  <dt>Last change</dt><dd>${a.last_changed || "—"}</dd>
  <dt>Checksum</dt>
  <dd><code>${a.checksum || "—"}</code>${a.changed ? html` <span class="badge">changed since last ingest</span>` : ""}</dd>
  ${a.children.length ? html`<dt>Sub-agencies</dt><dd>${a.children.map((c) => html`<a href="${agencyHref(c)}">${c}</a><br>`)}</dd>` : ""}
</dl>
<h3>Top review candidates</h3>
<div class="table-wrap"><table class="parts" id="detail-candidates"></table></div>
<p class="sub">${candidatesNote({ ...candidates, candidates: candidates.candidates.slice(0, 5) })}</p>
<h3>Size over time (daily refreshes)</h3>
${trend.days.length > 1 ? html`<div class="chart-box"><canvas id="trend" aria-label="Words per daily refresh"></canvas></div>`
  : html`<p class="note">Daily snapshots start ${trend.days[0]?.date ?? "with the next refresh"}; this chart grows with each refresh.</p>`}
<h3>Section changes per year</h3>
<div class="chart-box"><canvas data-testid="history" aria-label="Section changes per year"></canvas></div>
<p class="note">Recorded section changes since 2017 (eCFR versioner), attributed by current ownership. 2017-01-01 is an
  empirical cutoff: earlier rows are the eCFR baseline load.</p>
<h3>Statutes behind the most text</h3>
<ul>${a.top_statutes.length ? a.top_statutes.map((s) => html`<li>${s.cite}: ${num(s.words)} words in ${num(s.parts)} parts
  (${pct(s.words / a.words)} of this agency's text)</li>`) : html`<li>None cited</li>`}</ul>
<p class="note">From each part's authority note (only the first section after each "U.S.C."). A citation shows where a
  rule claims its power, not whether the statute requires it; procedural cites such as 5 U.S.C. 553 appear too.</p>
<h3>Largest parts</h3>
<ul>${a.top_parts.map((p) => html`<li>${p.title} CFR ${p.part}: ${p.heading} (${num(p.words)} words)</li>`)}</ul>
<p class="note">Sentence types come from a transparent rule-based classifier (first match wins: definition, prohibition,
  paperwork, obligation, permission, other); the sentence splitter and syllable counts are approximate.</p>`.text;
  const table = /** @type {HTMLTableElement} */ (panel.querySelector("#detail-candidates"));
  sortable(table, candidateColumns, { sort: "rank", dir: "ascending", empty: "No ranked parts." })(candidates.candidates.slice(0, 5));
  historyChart(/** @type {HTMLCanvasElement} */ (panel.querySelector("[data-testid=history]")), history.years);
  const canvas = /** @type {HTMLCanvasElement | null} */ (panel.querySelector("#trend"));
  if (canvas) trendChart(canvas, trend.days);
}
