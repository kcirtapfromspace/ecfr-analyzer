// Shared UI pieces: an escaping html`` tag, number formats, sorting and the sortable table component.
// Everything but sortable() is pure, so it is unit-tested with node:test (app/tests/js).

/**
 * @typedef {{slug: string, name: string, short_name: string | null, parent_slug: string | null, words: number,
 *   density: number | null, stale_share: number | null, flagged_parts: number, changed: boolean}} AgencyRow
 * @typedef {"ascending" | "descending"} Direction
 * @typedef {string | number | bigint | boolean | null | undefined} Value
 */
/**
 * A table column: its header, how a row's cell renders, and the value it sorts by (default: row[key]).
 * @template T
 * @typedef {{key: string, label: string, cell: (row: T) => unknown, value?: (row: T) => Value}} Column
 */

/** Markup that is already safe; html`` keeps it as is and escapes everything else. */
export class Safe {
  /** @param {string} text */
  constructor(text) { this.text = text; }
  toString() { return this.text; }
}
/** @type {Record<string, string>} */
const ENTITIES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
/** @param {unknown} v @returns {string} */
const fill = (v) => v instanceof Safe ? v.text : Array.isArray(v) ? v.map(fill).join("")
  : v == null || v === false ? "" : [...String(v)].map((c) => ENTITIES[c] ?? c).join("");
/** Template tag: escapes interpolated values, joins arrays, and nests other html`` results unescaped. */
export const html = (/** @type {TemplateStringsArray} */ strings, /** @type {unknown[]} */ ...values) =>
  new Safe(strings.reduce((out, s, i) => out + fill(values[i - 1]) + s));

/** @param {number | null | undefined} n */
export const num = (n) => (n == null ? "—" : n.toLocaleString("en-US"));
/** @param {number | null | undefined} x */
export const f1 = (x) => (x == null ? "—" : x.toFixed(1));
/** @param {number | null | undefined} x */
export const pct = (x) => (x == null ? "—" : `${(100 * x).toFixed(1)}%`);
/** @param {number} x */
export const signed = (x) => `${x >= 0 ? "+" : ""}${x.toFixed(1)}`;

/** Fetch JSON, failing on HTTP errors (GitHub Pages answers a missing file with an HTML 404 page). @param {string} url */
export async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return response.json();
}

/** Text sorts ascending first, everything else descending. @param {Value} sample @returns {Direction} */
export const firstDirection = (sample) => (typeof sample === "string" ? "ascending" : "descending");

/**
 * Sort rows by a value: text case-insensitively, nulls lowest.
 * @template T @param {T[]} rows @param {(row: T) => Value} by @param {Direction} dir @returns {T[]}
 */
export function sortRows(rows, by, dir) {
  const key = (/** @type {T} */ row) => { const v = by(row); return typeof v === "string" ? v.toLowerCase() : v; };
  /** @param {Value} x @param {Value} y */
  const order = (x, y) => (x == null ? (y == null ? 0 : -1) : y == null ? 1 : x < y ? -1 : x > y ? 1 : 0);
  const sign = dir === "ascending" ? 1 : -1;
  return [...rows].sort((a, b) => sign * order(key(a), key(b)));
}

/**
 * Agencies matching a search on name and abbreviation; an empty search shows top-level agencies only.
 * @param {AgencyRow[]} rows @param {string} query
 */
export function filterAgencies(rows, query) {
  const q = query.trim().toLowerCase();
  if (!q) return rows.filter((a) => !a.parent_slug);
  return rows.filter((a) => `${a.name} ${a.short_name ?? ""}`.toLowerCase().includes(q));
}

/**
 * Render rows into a table whose headers sort on click (again to reverse), shown by aria-sort and ▲/▼.
 * With `slug`, rows carry data-slug and a click anywhere on a row follows its first link.
 * Returns a function that redraws with new rows, keeping the sort.
 * @template T
 * @param {HTMLTableElement} table
 * @param {Column<T>[]} columns
 * @param {{sort?: string, dir?: Direction, empty?: string, slug?: (row: T) => string}} [options]
 */
export function sortable(table, columns, { sort, dir = "descending", empty = "No rows.", slug } = {}) {
  let rows = /** @type {T[]} */ ([]);
  /** @param {Column<T>} c @returns {(row: T) => Value} */
  const valueOf = (c) => c.value ?? ((row) => /** @type {Record<string, Value>} */ (row)[c.key]);
  const draw = () => {
    const column = columns.find((c) => c.key === sort);
    const shown = column ? sortRows(rows, valueOf(column), dir) : rows;
    table.innerHTML = html`<thead><tr>${columns.map((c) =>
      html`<th data-sort="${c.key}" aria-sort="${c.key === sort ? dir : "none"}">${c.label}</th>`)}</tr></thead>
      <tbody>${shown.length ? shown.map((r) => html`<tr ${slug ? html`data-slug="${slug(r)}"` : ""}>${
        columns.map((c) => html`<td>${c.cell(r)}</td>`)}</tr>`) : html`<tr><td colspan="${columns.length}">${empty}</td></tr>`}
      </tbody>`.text;
  };
  table.onclick = (event) => {
    const target = /** @type {Element} */ (event.target);
    const key = target.closest("th")?.getAttribute("data-sort");
    const column = columns.find((c) => c.key === key);
    if (column) {
      dir = key === sort ? (dir === "ascending" ? "descending" : "ascending")
        : firstDirection(rows.map(valueOf(column)).find((v) => v != null));
      sort = column.key;
      draw();
    } else if (!target.closest("a")) {
      target.closest("tr[data-slug]")?.querySelector("a")?.click();
    }
  };
  return (/** @type {T[]} */ next) => { rows = next; draw(); };
}
