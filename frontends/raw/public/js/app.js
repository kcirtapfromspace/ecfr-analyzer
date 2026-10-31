// Wires the page: fetch the static JSON, render the table, handle sort/search/detail.
import { historyChart, scatterChart } from "./charts.js";
import { filterRows, firstDirection, formatDecimal, formatInt, formatPercent, sortRows } from "./table.js";

/** @typedef {import("./table.js").Agency} Agency */
/** @typedef {import("./table.js").SortKey} SortKey */
/** @typedef {import("./table.js").Direction} Direction */

/** @param {string} url */
const getJSON = async (url) => (await fetch(url)).json();
/** @template {Element} T @param {string} testid @returns {T} */
const byTestId = (testid) => /** @type {T} */ (document.querySelector(`[data-testid="${testid}"]`));

/** @type {Agency[]} */
const agencies = await getJSON("api/agencies.json");
const table = byTestId(/** @type {const} */ ("agencies"));
const search = /** @type {HTMLInputElement} */ (byTestId("search"));
let sortKey = /** @type {SortKey} */ ("words");
let direction = /** @type {Direction} */ ("descending");

/** @param {Agency} a */
function row(a) {
  const tr = document.createElement("tr");
  tr.dataset.slug = a.slug;
  const name = a.short_name ? `${a.name} (${a.short_name})` : a.name;
  for (const text of [name, formatInt(a.words), formatDecimal(a.density), formatPercent(a.stale_share), formatInt(a.flagged_parts)]) {
    tr.insertCell().textContent = text;
  }
  tr.addEventListener("click", () => showDetail(a.slug));
  return tr;
}

function render() {
  const rows = sortRows(filterRows(agencies, search.value), sortKey, direction);
  /** @type {HTMLTableElement} */ (table).tBodies[0].replaceChildren(...rows.map(row));
  for (const th of table.querySelectorAll("th")) {
    th.setAttribute("aria-sort", th.getAttribute("data-sort") === sortKey ? direction : "none");
  }
}

/** @param {string} slug */
async function showDetail(slug) {
  const [agency, history] = await Promise.all([getJSON(`api/agencies/${slug}.json`), getJSON(`api/agencies/${slug}/history.json`)]);
  /** @type {HTMLElement} */ (document.getElementById("detail")).hidden = false;
  byTestId("detail-name").textContent = agency.name;
  byTestId("detail-words").textContent = formatInt(agency.words);
  byTestId("detail-density").textContent = formatDecimal(agency.density);
  historyChart(byTestId("history"), history.years);
}

table.querySelector("thead")?.addEventListener("click", (event) => {
  const key = /** @type {SortKey | undefined} */ (/** @type {HTMLElement} */ (event.target).closest("th")?.dataset.sort);
  if (!key) return;
  direction = key === sortKey ? (direction === "ascending" ? "descending" : "ascending") : firstDirection(key);
  sortKey = key;
  render();
});
search.addEventListener("input", render);
scatterChart(byTestId("scatter"), agencies.filter((a) => !a.parent_slug && a.words >= 1000), showDetail);
render();
