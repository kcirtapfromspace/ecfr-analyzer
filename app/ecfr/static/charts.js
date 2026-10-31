// Chart.js charts (Chart is the global from the CDN build, declared in types/globals.d.ts).
import { num } from "./ui.js";

/** @typedef {import("./ui.js").AgencyRow} AgencyRow */
/** @typedef {{year: number, substantive: number, nonsubstantive: number, removed: number}} Year */
/** @typedef {{date: string, words: number}} Day */

const css = (/** @type {string} */ name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const axis = (/** @type {string} */ text, extra = {}) => ({
  ...extra, title: { display: !!text, text, color: css("--muted") },
  ticks: { color: css("--muted") }, grid: { color: css("--line") },
});
/** @param {{x: number, y: number}[]} data */
const guide = (data) => ({ data, showLine: true, pointRadius: 0, borderWidth: 1, borderDash: [4, 4], borderColor: css("--muted") });
/** @param {number[]} xs */
const median = (xs) => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)];

/** Destroy the charts inside an element before its content is replaced. @param {Element} root */
export const destroyCharts = (root) => root.querySelectorAll("canvas").forEach((c) => Chart.getChart(c)?.destroy());

/**
 * Words (log scale) vs. restriction density with median guides; clicking a point picks that agency.
 * @param {HTMLCanvasElement} canvas @param {AgencyRow[]} agencies @param {(slug: string) => void} pick
 */
export function scatterChart(canvas, agencies, pick) {
  const rows = agencies.filter((a) => a.density != null);
  const words = rows.map((a) => a.words), density = rows.map((a) => /** @type {number} */ (a.density));
  const [mx, my] = [median(words), median(density)];
  return new Chart(canvas, {
    type: "scatter",
    data: { datasets: [
      { data: rows.map((a, i) => ({ x: words[i], y: density[i] })), backgroundColor: css("--s1") },
      guide([{ x: mx, y: 0 }, { x: mx, y: Math.max(...density) }]),
      guide([{ x: Math.min(...words), y: my }, { x: Math.max(...words), y: my }]),
    ] },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { filter: (/** @type {any} */ i) => i.datasetIndex === 0, callbacks: {
        label: (/** @type {any} */ c) => `${rows[c.dataIndex].short_name || rows[c.dataIndex].name}: ${num(c.raw.x)} words, ${c.raw.y.toFixed(1)} per 1k` } } },
      onClick: (/** @type {unknown} */ _, /** @type {{datasetIndex: number, index: number}[]} */ hits) => {
        const hit = hits.find((h) => h.datasetIndex === 0);
        if (hit) pick(rows[hit.index].slug);
      },
      scales: { x: axis("Words (log scale)", { type: "logarithmic" }), y: axis("Restriction terms per 1,000 words") },
    },
  });
}

/** Stacked bars of section changes per year. @param {HTMLCanvasElement} canvas @param {Year[]} years */
export function historyChart(canvas, years) {
  const series = /** @type {const} */ ([["substantive", "Substantive", "--s1"], ["nonsubstantive", "Non-substantive", "--s2"], ["removed", "Removed", "--s3"]]);
  return new Chart(canvas, {
    type: "bar",
    data: {
      labels: years.map((y) => y.year),
      datasets: series.map(([key, label, color]) => ({ label, data: years.map((y) => y[key]), backgroundColor: css(color) })),
    },
    options: {
      maintainAspectRatio: false, plugins: { legend: { labels: { color: css("--ink") } } },
      scales: { x: axis("", { stacked: true }), y: axis("", { stacked: true }) },
    },
  });
}

/** An agency's words at each daily refresh. @param {HTMLCanvasElement} canvas @param {Day[]} days */
export function trendChart(canvas, days) {
  return new Chart(canvas, {
    type: "line",
    data: { labels: days.map((d) => d.date), datasets: [{ data: days.map((d) => d.words), borderColor: css("--s1"), backgroundColor: css("--s1") }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: axis(""), y: axis("Words") } },
  });
}
