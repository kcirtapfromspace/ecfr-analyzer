// The index page: refresh line, summary cards, review candidates, recent changes, scatter plot, agency table and
// SQL explorer. The URL hash (#agency/<slug>) picks the agency shown in the detail panel.
import { scatterChart } from "./charts.js";
import { agencyColumns, agencyHref, candidateColumns, candidatesNote, changeColumns } from "./columns.js";
import { showAgency } from "./detail.js";
import { explore } from "./explore.js";
import { filterAgencies, getJSON, html, num, pct, sortable } from "./ui.js";

/**
 * GET api/meta.json; only the fields this page reads.
 * @typedef {{ecfr_date: string, ingested_at: string, previous_ecfr_date: string | null, mode: string,
 *   titles: number[], titles_processed: number[], parts_changed: {modified: number, added: number, removed: number},
 *   words: number, parts: number, change_rows: number, sections: number, stale_sections: number,
 *   authority_words: {statute: number}, eligible: number}} Meta
 */

/** @template {HTMLElement} T @param {string} selector @returns {T} */
const $ = (selector) => /** @type {T} */ (document.querySelector(selector));
const [meta, agencies, changes] = /** @type {[Meta, import("./ui.js").AgencyRow[], {changes: import("./columns.js").Change[]}]} */ (
  await Promise.all([getJSON("api/meta.json"), getJSON("api/agency-table.json"), getJSON("api/changes.json")]));

const delta = meta.parts_changed;
$("#refresh").innerHTML = html`Last refresh ${meta.ingested_at} · eCFR data as of ${meta.ecfr_date}
  ${meta.previous_ecfr_date ? `· since ${meta.previous_ecfr_date}: ${delta.modified} parts modified, ${delta.added} added,
  ${delta.removed} removed` : ""} · ${meta.titles_processed.length} of ${meta.titles.length} titles reprocessed (${meta.mode})
  · <a href="api/openapi.json">JSON API</a>`.text;

const cards = [
  [num(meta.words), "Words in regulations"],
  [num(meta.parts), "Parts"],
  [num(meta.change_rows), "Section changes since 2017"],
  [pct(meta.stale_sections / meta.sections), "Sections unchanged since 2017"],
  [pct(meta.authority_words.statute / meta.words), "Words citing a specific statute"],
  [num(meta.eligible), "Parts ranked for review"],
];
$("#cards").innerHTML = html`${cards.map(([value, label]) => html`<div class="card"><b>${value}</b><span>${label}</span></div>`)}`.text;

// Review candidates, for all agencies or the one picked in the filter.
const filter = /** @type {HTMLSelectElement} */ ($("#agency-filter"));
filter.insertAdjacentHTML("beforeend", html`${agencies.filter((a) => a.flagged_parts).map((a) =>
  html`<option value="${a.slug}">${a.name} (${a.flagged_parts} flagged)</option>`)}`.text);
const showCandidates = sortable($("#candidates"), candidateColumns, { sort: "rank", dir: "ascending", empty: "No ranked parts." });
filter.onchange = async () => {
  const slug = filter.value;
  const candidates = /** @type {import("./columns.js").Candidates} */ (
    await getJSON(`ui/candidates/${slug ? encodeURIComponent(slug) : "all"}.json`));
  if (slug !== filter.value) return; // a later pick is loading
  showCandidates(candidates.candidates);
  $("#candidates-note").textContent = candidatesNote(candidates);
};
filter.onchange(new Event("change"));

sortable($("#changes"), changeColumns, { empty: "No changes recorded yet: the change log starts with the first daily refresh." })(
  changes.changes);

const open = (/** @type {string} */ slug) => (location.hash = agencyHref(slug));
scatterChart($("[data-testid=scatter]"), agencies.filter((a) => !a.parent_slug && a.words >= 1000), open);

const search = /** @type {HTMLInputElement} */ ($("[data-testid=search]"));
const showAgencies = sortable($("[data-testid=agencies]"), agencyColumns, { sort: "words", slug: (a) => a.slug });
search.oninput = () => showAgencies(filterAgencies(agencies, search.value));
showAgencies(filterAgencies(agencies, search.value));

explore(meta.titles.map(String));

const route = () => {
  const match = location.hash.match(/^#agency\/(.+)$/);
  if (match) showAgency($("#detail"), decodeURIComponent(match[1]));
};
window.onhashchange = route;
route();
