// Pure helpers for the server-rendered table. The rows live in the DOM, so these work on cell values;
// app.js applies them to <tr> elements.

/** @typedef {"ascending" | "descending"} Direction */

/** Text columns start ascending, number columns descending. @param {string} key @returns {Direction} */
export const firstDirection = (key) => (key === "name" ? "ascending" : "descending");

/** Sort value of a cell's data-v: text for the name column, otherwise a number with blanks lowest. */
export const sortValue = (/** @type {string} */ key, /** @type {string} */ v) =>
  key === "name" ? v : v === "" ? -Infinity : Number(v);

/** @param {string | number} x @param {string | number} y @param {Direction} dir */
export const compare = (x, y, dir) => (dir === "ascending" ? 1 : -1) * (x < y ? -1 : x > y ? 1 : 0);

/** Whether a row shows for a query: sub-agencies appear only in search results. */
export function visible(/** @type {string} */ haystack, /** @type {boolean} */ isChild, /** @type {string} */ query) {
  const q = query.trim().toLowerCase();
  return q ? haystack.includes(q) : !isChild;
}
