// The page as Preact components written with htm tagged templates: no build step.
import { html, render } from "htm/preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { historyChart, scatterChart } from "./charts.js";
import { filterRows, firstDirection, formatDecimal, formatInt, formatPercent, sortRows } from "./table.js";

/** @typedef {import("./table.js").Agency} Agency */
/** @typedef {import("./table.js").SortKey} SortKey */
/** @typedef {import("./table.js").Direction} Direction */
/** @typedef {{agency: Agency, years: import("./charts.js").Year[]}} Detail */

/** @param {string} url */
const getJSON = async (url) => (await fetch(url)).json();

/** @type {[SortKey, string][]} */
const columns = [
  ["name", "Agency"],
  ["words", "Words"],
  ["density", "Restrictions / 1k"],
  ["stale_share", "Unchanged since 2017"],
  ["flagged_parts", "Flagged parts"],
];

/** A canvas whose chart is drawn on mount and destroyed on unmount (re-key it to redraw). */
function ChartCanvas(/** @type {{testid: string, draw: (c: HTMLCanvasElement) => {destroy(): void}}} */ { testid, draw }) {
  const ref = useRef(/** @type {HTMLCanvasElement | null} */ (null));
  useEffect(() => {
    const chart = draw(/** @type {HTMLCanvasElement} */ (ref.current));
    return () => chart.destroy();
  }, []);
  return html`<div class="chart"><canvas data-testid=${testid} ref=${ref}></canvas></div>`;
}

function AgencyDetail(/** @type {{slug: string}} */ { slug }) {
  const [data, setData] = useState(/** @type {Detail | null} */ (null));
  useEffect(() => {
    Promise.all([getJSON(`api/agencies/${slug}.json`), getJSON(`api/agencies/${slug}/history.json`)]).then(([agency, history]) =>
      setData({ agency, years: history.years }),
    );
  }, [slug]);
  if (!data) return null;
  return html`<aside>
    <h2 data-testid="detail-name">${data.agency.name}</h2>
    <dl>
      <dt>Words</dt><dd data-testid="detail-words">${formatInt(data.agency.words)}</dd>
      <dt>Restrictions / 1k</dt><dd data-testid="detail-density">${formatDecimal(data.agency.density)}</dd>
    </dl>
    <${ChartCanvas} testid="history" draw=${(/** @type {HTMLCanvasElement} */ c) => historyChart(c, data.years)} />
  </aside>`;
}

function App(/** @type {{agencies: Agency[]}} */ { agencies }) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState(/** @type {{key: SortKey, dir: Direction}} */ ({ key: "words", dir: "descending" }));
  const [selected, setSelected] = useState(/** @type {string | null} */ (null));
  const rows = sortRows(filterRows(agencies, query), sort.key, sort.dir);
  const plotted = agencies.filter((a) => !a.parent_slug && a.words >= 1000);
  /** @param {SortKey} key */
  const sortBy = (key) =>
    setSort(({ key: current, dir }) => ({
      key,
      dir: key === current ? (dir === "ascending" ? "descending" : "ascending") : firstDirection(key),
    }));

  return html`<h1>eCFR Analyzer</h1>
    <main>
      <section>
        <${ChartCanvas} testid="scatter" draw=${(/** @type {HTMLCanvasElement} */ c) => scatterChart(c, plotted, setSelected)} />
        <input
          type="search"
          data-testid="search"
          placeholder="Filter agencies (includes sub-agencies)"
          value=${query}
          onInput=${(/** @type {InputEvent} */ e) => setQuery(/** @type {HTMLInputElement} */ (e.currentTarget).value)}
        />
        <table data-testid="agencies">
          <thead>
            <tr>
              ${columns.map(
                ([key, label]) =>
                  html`<th data-sort=${key} aria-sort=${key === sort.key ? sort.dir : "none"} onClick=${() => sortBy(key)}>${label}</th>`,
              )}
            </tr>
          </thead>
          <tbody>
            ${rows.map(
              (a) => html`<tr key=${a.slug} data-slug=${a.slug} onClick=${() => setSelected(a.slug)}>
                <td>${a.short_name ? `${a.name} (${a.short_name})` : a.name}</td>
                <td>${formatInt(a.words)}</td>
                <td>${formatDecimal(a.density)}</td>
                <td>${formatPercent(a.stale_share)}</td>
                <td>${formatInt(a.flagged_parts)}</td>
              </tr>`,
            )}
          </tbody>
        </table>
      </section>
      ${selected && html`<${AgencyDetail} key=${selected} slug=${selected} />`}
    </main>`;
}

render(html`<${App} agencies=${await getJSON("api/agencies.json")} />`, document.body);
