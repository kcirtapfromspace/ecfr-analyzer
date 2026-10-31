// The page as plain function calls: van.tags builds elements, and anything that reads a van.state re-renders.
import van from "vanjs-core";
import { historyChart, scatterChart } from "./charts.js";
import { filterRows, firstDirection, formatDecimal, formatInt, formatPercent, sortRows } from "./table.js";

/** @typedef {import("./table.js").Agency} Agency */
/** @typedef {import("./table.js").SortKey} SortKey */
/** @typedef {import("./table.js").Direction} Direction */
/** @typedef {{agency: Agency, years: import("./charts.js").Year[]}} Detail */

const { aside, canvas, dd, div, dl, dt, h1, h2, input, main, section, table, tbody, td, th, thead, tr } = van.tags;

/** @param {string} url */
const getJSON = async (url) => (await fetch(url)).json();
/** @type {Agency[]} */
const agencies = await getJSON("api/agencies.json");

const query = van.state("");
const sortKey = van.state(/** @type {SortKey} */ ("words"));
const direction = van.state(/** @type {Direction} */ ("descending"));
const detail = van.state(/** @type {Detail | null} */ (null));

/** @type {[SortKey, string][]} */
const columns = [
  ["name", "Agency"],
  ["words", "Words"],
  ["density", "Restrictions / 1k"],
  ["stale_share", "Unchanged since 2017"],
  ["flagged_parts", "Flagged parts"],
];

/** @param {SortKey} key */
function sortBy(key) {
  direction.val = key === sortKey.val ? (direction.val === "ascending" ? "descending" : "ascending") : firstDirection(key);
  sortKey.val = key;
}

/** @param {string} slug */
async function open(slug) {
  const [agency, history] = await Promise.all([getJSON(`api/agencies/${slug}.json`), getJSON(`api/agencies/${slug}/history.json`)]);
  detail.val = { agency, years: history.years };
}

/** A canvas whose chart is drawn once it is in the document. @param {string} testid @param {(c: HTMLCanvasElement) => void} draw */
function chart(testid, draw) {
  const c = canvas({ "data-testid": testid });
  requestAnimationFrame(() => draw(c));
  return div({ class: "chart" }, c);
}

/** @param {Agency} a */
const row = (a) =>
  tr(
    { "data-slug": a.slug, onclick: () => open(a.slug) },
    td(a.short_name ? `${a.name} (${a.short_name})` : a.name),
    td(formatInt(a.words)),
    td(formatDecimal(a.density)),
    td(formatPercent(a.stale_share)),
    td(formatInt(a.flagged_parts)),
  );

/** @param {Detail | null} d */
const detailView = (d) =>
  d
    ? aside(
        h2({ "data-testid": "detail-name" }, d.agency.name),
        dl(
          dt("Words"),
          dd({ "data-testid": "detail-words" }, formatInt(d.agency.words)),
          dt("Restrictions / 1k"),
          dd({ "data-testid": "detail-density" }, formatDecimal(d.agency.density)),
        ),
        chart("history", (c) => historyChart(c, d.years)),
      )
    : aside();

const plotted = agencies.filter((a) => !a.parent_slug && a.words >= 1000);
van.add(
  document.body,
  h1("eCFR Analyzer"),
  main(
    section(
      chart("scatter", (c) => scatterChart(c, plotted, open)),
      input({
        type: "search",
        "data-testid": "search",
        placeholder: "Filter agencies (includes sub-agencies)",
        oninput: (/** @type {InputEvent} */ e) => (query.val = /** @type {HTMLInputElement} */ (e.target).value),
      }),
      table(
        { "data-testid": "agencies" },
        thead(
          tr(
            columns.map(([key, label]) =>
              th({ "data-sort": key, "aria-sort": () => (key === sortKey.val ? direction.val : "none"), onclick: () => sortBy(key) }, label),
            ),
          ),
        ),
        () => tbody(sortRows(filterRows(agencies, query.val), sortKey.val, direction.val).map(row)),
      ),
    ),
    () => detailView(detail.val),
  ),
);
