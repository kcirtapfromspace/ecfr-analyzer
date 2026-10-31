// Charts are declared by the server as <canvas data-chart='{"kind": ..., "data": ...}'> and drawn after every htmx swap.
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const fmt = n => Number(n).toLocaleString("en-US");
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const showAgency = slug => htmx.ajax("GET", `ui/agency/${slug}.html`, "#detail");
const axis = (text, extra = {}) => ({
  ...extra, title: { display: !!text, text, color: css("--muted") },
  ticks: { color: css("--muted") }, grid: { color: css("--line") },
});
const guide = data => ({ data, showLine: true, pointRadius: 0, borderWidth: 1, borderDash: [4, 4], borderColor: css("--muted") });

const charts = {
  trend: days => ({
    type: "line",
    data: { labels: days.map(d => d.date), datasets: [{ data: days.map(d => d.words), borderColor: css("--s1"), backgroundColor: css("--s1") }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: axis(), y: axis("Words") } },
  }),
  scatter: rows => {
    const median = xs => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)];
    const words = rows.map(r => r[1]), density = rows.map(r => r[2]);
    const [mx, my] = [median(words), median(density)];
    return {
      type: "scatter",
      data: { datasets: [
        { data: rows.map(r => ({ x: r[1], y: r[2] })), backgroundColor: css("--s1") },
        guide([{ x: mx, y: 0 }, { x: mx, y: Math.max(...density) }]),
        guide([{ x: Math.min(...words), y: my }, { x: Math.max(...words), y: my }]),
      ] },
      options: {
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { filter: i => i.datasetIndex === 0, callbacks: {
          label: c => `${rows[c.dataIndex][0]}: ${fmt(c.raw.x)} words, ${c.raw.y.toFixed(1)} per 1k` } } },
        onClick: (_, els) => { const e = els.find(e => e.datasetIndex === 0); if (e) showAgency(rows[e.index][3]); },
        scales: { x: axis("Words (log scale)", { type: "logarithmic" }), y: axis("Restriction terms per 1,000 words") },
      },
    };
  },
  history: years => ({
    type: "bar",
    data: {
      labels: years.map(y => y.year),
      datasets: [["substantive", "Substantive", "--s1"], ["nonsubstantive", "Non-substantive", "--s2"], ["removed", "Removed", "--s3"]]
        .map(([k, label, color]) => ({ label, data: years.map(y => y[k]), backgroundColor: css(color) })),
    },
    options: {
      maintainAspectRatio: false, plugins: { legend: { labels: { color: css("--ink") } } },
      scales: { x: axis("", { stacked: true }), y: axis("", { stacked: true }) },
    },
  }),
};

htmx.onLoad(root => root.querySelectorAll("canvas[data-chart]").forEach(canvas => {
  const spec = JSON.parse(canvas.dataset.chart);
  Chart.getChart(canvas)?.destroy();
  new Chart(canvas, charts[spec.kind](spec.data));
}));

// Explore panel: DuckDB-WASM queries the server's Parquet files over HTTP Range requests, entirely in the browser.
let duck = null;
async function connectDuckDB() {
  const duckdb = await import("https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm");
  const bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
  const workerUrl = URL.createObjectURL(new Blob([`importScripts("${bundle.mainWorker}");`], { type: "text/javascript" }));
  const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), new Worker(workerUrl));
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  URL.revokeObjectURL(workerUrl);
  const texts = document.getElementById("explore").dataset.titles.split(",").map(n => `text/title-${n}.parquet`);
  for (const name of ["parts", "agencies", "agency_parts", "versions", "agency_history", "part_changes"].map(n => `${n}.parquet`).concat(texts)) {
    await db.registerFileURL(name, new URL(`data/${name}`, location.href).href, duckdb.DuckDBDataProtocol.HTTP, false);
  }
  const conn = await db.connect();
  await conn.query(`CREATE VIEW parts_text AS SELECT * FROM read_parquet([${texts.map(t => `'${t}'`).join(", ")}])`);
  return conn;
}
const cell = v => {  // Arrow values: scalars and bigints, lists/structs (toJSON), 128-bit integers (toString)
  if (v == null || typeof v !== "object") return v == null ? "" : String(v);
  const j = v.toJSON?.();
  return j && typeof j === "object" ? JSON.stringify(j, (_, x) => typeof x === "bigint" ? `${x}` : x) : String(v);
};

document.addEventListener("click", async e => {
  if (e.target.id !== "run") return;
  const status = document.getElementById("status"), out = document.getElementById("result");
  status.textContent = "Running…";
  let conn;
  try {
    conn = await (duck ??= connectDuckDB());
  } catch (err) {
    duck = null;  // let the next click retry loading DuckDB-WASM
    status.textContent = "Could not load DuckDB-WASM: " + (err.message || err);
    return;
  }
  try {
    const started = performance.now();
    const table = await conn.query(document.getElementById("sql").value);
    const cols = table.schema.fields.map(f => f.name);
    const rows = table.toArray().slice(0, 500);
    out.innerHTML = `<table><thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${
      rows.map(r => `<tr>${cols.map(c => `<td>${esc(cell(r[c]))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    status.textContent = `${fmt(table.numRows)} rows in ${Math.round(performance.now() - started)} ms, computed in your browser`
      + (table.numRows > 500 ? " (showing 500)" : "");
  } catch (err) {
    status.textContent = "Query error: " + (err.message || err);
  }
});

// Sort any table by clicking a header; click again to reverse. Cells with data-v sort as numbers.
document.addEventListener("click", e => {
  const th = e.target.closest("thead th");
  if (!th) return;
  const table = th.closest("table"), col = th.cellIndex, body = table.tBodies[0];
  const numeric = body.rows[0]?.cells[col]?.dataset.v !== undefined;
  const dir = th.dataset.dir ? (th.dataset.dir === "asc" ? "desc" : "asc") : numeric ? "desc" : "asc";
  table.querySelectorAll("thead th").forEach(h => delete h.dataset.dir);
  th.dataset.dir = dir;
  const key = td => !td ? "" : td.dataset.v === undefined ? td.textContent.trim().toLowerCase()
    : td.dataset.v === "" ? -Infinity : Number(td.dataset.v);
  const rows = [...body.rows].sort((a, b) => { const x = key(a.cells[col]), y = key(b.cells[col]); return (x > y) - (x < y); });
  body.append(...(dir === "desc" ? rows.reverse() : rows));
});

// Search spans every agency; with no query only top-level agencies show.
document.addEventListener("input", e => {
  if (e.target.id !== "q") return;
  const q = e.target.value.trim().toLowerCase();
  for (const tr of document.querySelectorAll("#rows tr")) tr.hidden = q ? !tr.dataset.search.includes(q) : tr.classList.contains("child");
});

document.addEventListener("change", e => {
  if (e.target.name === "agency") htmx.ajax("GET", `ui/candidates/${e.target.value || "all"}.html`, "#candidates");
});
