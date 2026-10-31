// What each table shows: agencies, review candidates and part changes (the shapes are in CONTRACT.md).
import { html, f1, num, pct, signed } from "./ui.js";

/** @typedef {import("./ui.js").AgencyRow} AgencyRow */
/**
 * @typedef {{rank: number, title: number, part: string, heading: string, words: number, score: number,
 *   flagged: boolean, inputs: Record<string, number>, z: Record<string, number>}} Candidate
 * @typedef {{agency: string | null, eligible: number, flagged: number, candidates: Candidate[]}} Candidates
 * @typedef {{ecfr_date: string, title: number, part: string, heading: string, change: string,
 *   words_before: number | null, words_after: number | null}} Change
 */

/** The ranking inputs, in model.INPUTS order. */
const INPUTS = ["size", "density", "grade", "directive", "paperwork", "staleness"];

/** @param {string} slug */
export const agencyHref = (slug) => `#agency/${encodeURIComponent(slug)}`;
/** @param {{title: number, part: string, heading: string}} p */
const partLink = (p) => html`<a href="https://www.ecfr.gov/current/title-${p.title}/part-${p.part}" target="_blank"
  rel="noopener">${p.title} CFR ${p.part}</a> <span class="sub">${p.heading}</span>`;
/** @param {{title: number, part: string}} p */
const partName = (p) => `${p.title} CFR ${p.part}`;

/** @type {import("./ui.js").Column<AgencyRow>[]} */
export const agencyColumns = [
  { key: "name", label: "Agency", cell: (a) => html`<a href="${agencyHref(a.slug)}">${a.name}</a>${
    a.short_name ? html` <span class="sub">(${a.short_name})</span>` : ""}${a.changed ? html` <span class="badge">changed</span>` : ""}` },
  { key: "words", label: "Words", cell: (a) => num(a.words) },
  { key: "density", label: "Restrictions / 1k", cell: (a) => f1(a.density) },
  { key: "stale_share", label: "Unchanged since 2017", cell: (a) => pct(a.stale_share) },
  { key: "flagged_parts", label: "Flagged parts", cell: (a) => num(a.flagged_parts) },
];

/** @type {import("./ui.js").Column<Candidate>[]} */
export const candidateColumns = [
  { key: "rank", label: "Rank", cell: (c) => html`${num(c.rank)}${c.flagged ? html` <span class="badge">top 10%</span>` : ""}` },
  { key: "part", label: "Part", cell: partLink, value: partName },
  { key: "words", label: "Words", cell: (c) => num(c.words) },
  { key: "score", label: "Score", cell: (c) => c.score.toFixed(2) },
  ...INPUTS.map((k) => ({
    key: k, label: k, value: (/** @type {Candidate} */ c) => c.z[k],
    cell: (/** @type {Candidate} */ c) => html`<span class="${c.z[k] > 1 ? "hi" : c.z[k] < -1 ? "lo" : ""}"
      title="${k} = ${Number(c.inputs[k].toPrecision(3))}">${signed(c.z[k])}</span>`,
  })),
];

/** @param {Candidates} c */
export const candidatesNote = (c) => `${num(c.eligible)} parts ranked across the CFR; the top ${num(c.flagged)} are flagged.
  Showing ${c.candidates.length}; the JSON API has the top 500.`;

/** @type {import("./ui.js").Column<Change>[]} */
export const changeColumns = [
  { key: "ecfr_date", label: "eCFR date", cell: (c) => c.ecfr_date },
  { key: "part", label: "Part", cell: partLink, value: partName },
  { key: "change", label: "Change", cell: (c) => c.change },
  { key: "words_before", label: "Words before", cell: (c) => num(c.words_before) },
  { key: "words_after", label: "Words after", cell: (c) => num(c.words_after) },
];
