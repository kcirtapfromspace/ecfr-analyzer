// Chart.js wrappers. Chart is the global from the CDN UMD build (declared in globals.d.ts).

/** @typedef {import("./table.js").Agency} Agency */
/** @typedef {{year: number, substantive: number, nonsubstantive: number, removed: number}} Year */

/**
 * Words (log scale) vs. restriction density; clicking a point picks that agency.
 * @param {HTMLCanvasElement} canvas
 * @param {Agency[]} agencies
 * @param {(slug: string) => void} onPick
 */
export function scatterChart(canvas, agencies, onPick) {
  return new Chart(canvas, {
    type: "scatter",
    data: { datasets: [{ data: agencies.map((a) => ({ x: a.words, y: a.density })) }] },
    options: {
      maintainAspectRatio: false,
      onClick: (/** @type {unknown} */ _, /** @type {{index: number}[]} */ hits) => {
        if (hits.length) onPick(agencies[hits[0].index].slug);
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (/** @type {{dataIndex: number}} */ c) => agencies[c.dataIndex].name } },
      },
      scales: {
        x: { type: "logarithmic", title: { display: true, text: "Words (log scale)" } },
        y: { title: { display: true, text: "Restriction terms per 1,000 words" } },
      },
    },
  });
}

/**
 * Stacked bars of section changes per year; replaces any chart already on the canvas.
 * @param {HTMLCanvasElement} canvas
 * @param {Year[]} years
 */
export function historyChart(canvas, years) {
  Chart.getChart(canvas)?.destroy();
  const series = /** @type {const} */ ([
    ["substantive", "Substantive"],
    ["nonsubstantive", "Non-substantive"],
    ["removed", "Removed"],
  ]);
  return new Chart(canvas, {
    type: "bar",
    data: {
      labels: years.map((y) => y.year),
      datasets: series.map(([key, label]) => ({ label, data: years.map((y) => y[key]) })),
    },
    options: { maintainAspectRatio: false, scales: { x: { stacked: true }, y: { stacked: true } } },
  });
}
