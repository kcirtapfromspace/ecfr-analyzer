// DOM wiring for the pre-rendered page: sort and search the <tr> rows, and draw the charts that
// the server declares in data-chart whenever htmx swaps in content.
import { compare, firstDirection, sortValue, visible } from "./table.js";

const table = /** @type {HTMLTableElement} */ (document.querySelector('[data-testid="agencies"]'));
const body = table.tBodies[0];
const search = /** @type {HTMLInputElement} */ (document.querySelector('[data-testid="search"]'));

table.tHead?.addEventListener("click", (event) => {
  const th = /** @type {HTMLElement} */ (event.target).closest("th");
  if (!th?.dataset.sort) return;
  const key = th.dataset.sort;
  const current = th.getAttribute("aria-sort");
  const dir = current === "descending" ? "ascending" : current === "ascending" ? "descending" : firstDirection(key);
  for (const h of table.querySelectorAll("th")) h.setAttribute("aria-sort", "none");
  th.setAttribute("aria-sort", dir);
  /** @param {HTMLTableRowElement} tr */
  const value = (tr) => sortValue(key, tr.cells[th.cellIndex].dataset.v ?? "");
  body.append(...[...body.rows].sort((a, b) => compare(value(a), value(b), dir)));
});

search.addEventListener("input", () => {
  for (const tr of body.rows) tr.hidden = !visible(tr.dataset.search ?? "", tr.hasAttribute("data-child"), search.value);
});

/** @type {Record<string, (data: any) => object>} */
const charts = {
  scatter: (rows) => ({
    type: "scatter",
    data: { datasets: [{ data: rows.map((/** @type {any[]} */ r) => ({ x: r[1], y: r[2] })) }] },
    options: {
      maintainAspectRatio: false,
      onClick: (/** @type {unknown} */ _, /** @type {{index: number}[]} */ hits) =>
        hits.length && htmx.ajax("GET", `agency/${rows[hits[0].index][3]}.html`, "#detail"),
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (/** @type {any} */ c) => rows[c.dataIndex][0] } } },
      scales: {
        x: { type: "logarithmic", title: { display: true, text: "Words (log scale)" } },
        y: { title: { display: true, text: "Restriction terms per 1,000 words" } },
      },
    },
  }),
  history: (years) => ({
    type: "bar",
    data: {
      labels: years.map((/** @type {any} */ y) => y.year),
      datasets: ["substantive", "nonsubstantive", "removed"].map((key) => ({ label: key, data: years.map((/** @type {any} */ y) => y[key]) })),
    },
    options: { maintainAspectRatio: false, scales: { x: { stacked: true }, y: { stacked: true } } },
  }),
};

htmx.onLoad((/** @type {HTMLElement} */ root) => {
  for (const canvas of root.querySelectorAll("canvas[data-chart]")) {
    const spec = JSON.parse(/** @type {HTMLCanvasElement} */ (canvas).dataset.chart ?? "{}");
    Chart.getChart(canvas)?.destroy();
    new Chart(canvas, charts[spec.kind](spec.data));
  }
});
