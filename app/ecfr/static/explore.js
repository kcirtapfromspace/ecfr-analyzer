// Explore panel: DuckDB-WASM queries the site's Parquet files over HTTP Range requests, entirely in the browser.
import { num, sortable } from "./ui.js";

const DUCKDB = "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm";
const TABLES = ["parts", "agencies", "agency_parts", "versions", "agency_history", "part_changes"];

/** @param {string[]} titles CFR title numbers; their text is split into one Parquet file each */
async function connect(titles) {
  const duckdb = await import(DUCKDB);
  const bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
  const workerUrl = URL.createObjectURL(new Blob([`importScripts("${bundle.mainWorker}");`], { type: "text/javascript" }));
  const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), new Worker(workerUrl));
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  URL.revokeObjectURL(workerUrl);
  const texts = titles.map((n) => `text/title-${n}.parquet`);
  for (const name of TABLES.map((n) => `${n}.parquet`).concat(texts)) {
    await db.registerFileURL(name, new URL(`data/${name}`, location.href).href, duckdb.DuckDBDataProtocol.HTTP, false);
  }
  const conn = await db.connect();
  await conn.query(`CREATE VIEW parts_text AS SELECT * FROM read_parquet([${texts.map((t) => `'${t}'`).join(", ")}])`);
  return conn;
}

/** Arrow values: scalars and bigints, lists/structs (toJSON), 128-bit integers (toString). @param {any} v */
const cell = (v) => {
  if (v == null || typeof v !== "object") return v == null ? "" : String(v);
  const j = v.toJSON?.();
  return j && typeof j === "object" ? JSON.stringify(j, (_, x) => (typeof x === "bigint" ? `${x}` : x)) : String(v);
};

/** Wire the Run button. @param {string[]} titles */
export function explore(titles) {
  const status = /** @type {HTMLElement} */ (document.getElementById("status"));
  const result = /** @type {HTMLTableElement} */ (document.getElementById("result"));
  const sql = /** @type {HTMLTextAreaElement} */ (document.getElementById("sql"));
  /** @type {Promise<any> | null} */
  let duck = null;
  /** @type {HTMLElement} */ (document.getElementById("run")).onclick = async () => {
    status.textContent = "Running…";
    let conn;
    try {
      conn = await (duck ??= connect(titles));
    } catch (err) {
      duck = null; // let the next click retry loading DuckDB-WASM
      status.textContent = `Could not load DuckDB-WASM: ${/** @type {Error} */ (err).message || err}`;
      return;
    }
    try {
      const started = performance.now();
      const table = await conn.query(sql.value);
      /** @type {string[]} */
      const names = table.schema.fields.map((/** @type {{name: string}} */ f) => f.name);
      // Numbers sort as numbers; lists, structs and 128-bit integers sort by their text.
      const value = (/** @type {any} */ v) => (v != null && typeof v === "object" ? cell(v) : v);
      const columns = names.map((name) => ({ key: name, label: name, cell: (/** @type {any} */ r) => cell(r[name]),
        value: (/** @type {any} */ r) => value(r[name]) }));
      sortable(result, columns, { empty: "No rows." })(table.toArray().slice(0, 500));
      status.textContent = `${num(table.numRows)} rows in ${Math.round(performance.now() - started)} ms, computed in your browser`
        + (table.numRows > 500 ? " (showing 500)" : "");
    } catch (err) {
      status.textContent = `Query error: ${/** @type {Error} */ (err).message || err}`;
    }
  };
}
