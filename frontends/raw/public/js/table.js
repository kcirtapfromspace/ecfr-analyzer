// Pure table logic: no DOM, so it is unit-tested with node:test and type-checked with tsc --checkJs.

/**
 * @typedef {{slug: string, name: string, short_name: string | null, parent_slug: string | null,
 *   words: number, density: number | null, stale_share: number | null, flagged_parts: number}} Agency
 * @typedef {"name" | "words" | "density" | "stale_share" | "flagged_parts"} SortKey
 * @typedef {"ascending" | "descending"} Direction
 */

/** Text columns start ascending, number columns descending. @param {SortKey} key @returns {Direction} */
export const firstDirection = (key) => (key === "name" ? "ascending" : "descending");

/**
 * Sort agencies by one column; nulls rank lowest.
 * @param {Agency[]} rows
 * @param {SortKey} key
 * @param {Direction} dir
 * @returns {Agency[]}
 */
export function sortRows(rows, key, dir) {
  /** @param {Agency} a */
  const value = (a) => (key === "name" ? a.name.toLowerCase() : (a[key] ?? -Infinity));
  const sign = dir === "ascending" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = value(a);
    const y = value(b);
    return sign * (x < y ? -1 : x > y ? 1 : 0);
  });
}

/**
 * Agencies matching a search across name and abbreviation; an empty query shows top-level agencies only.
 * @param {Agency[]} rows
 * @param {string} query
 * @returns {Agency[]}
 */
export function filterRows(rows, query) {
  const q = query.trim().toLowerCase();
  if (!q) return rows.filter((a) => !a.parent_slug);
  return rows.filter((a) => `${a.name} ${a.short_name ?? ""}`.toLowerCase().includes(q));
}

/** @param {number | null} n */
export const formatInt = (n) => (n == null ? "—" : n.toLocaleString("en-US"));
/** @param {number | null} x */
export const formatDecimal = (x) => (x == null ? "—" : x.toFixed(1));
/** @param {number | null} x */
export const formatPercent = (x) => (x == null ? "—" : `${(100 * x).toFixed(1)}%`);
