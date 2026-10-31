import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { filterRows, sortRows } from "../src/components/table.js";

const agencies = JSON.parse(readFileSync(new URL("../../fixtures/api/agencies.json", import.meta.url), "utf8"));
const topLevel = filterRows(agencies, "");

test("density descending puts the Access Board first", () => {
  assert.equal(sortRows(topLevel, "density", "descending")[0].name, "Architectural and Transportation Barriers Compliance Board");
});

test("nulls go last when descending", () => {
  const rows = sortRows(agencies, "density", "descending");
  const firstNull = rows.findIndex((a) => a.density === null);
  assert.ok(firstNull > 0);
  assert.ok(rows.slice(firstNull).every((a) => a.density === null));
});

test("name ascending is case-insensitive", () => {
  assert.equal(sortRows(topLevel, "name", "ascending")[0].name, "Administrative Committee of the Federal Register");
});

test("search spans sub-agencies", () => {
  const hits = filterRows(agencies, "Occupational");
  assert.equal(hits.length, 2);
  assert.ok(hits.some((a) => a.parent_slug));
});

test("an empty query shows only top-level agencies", () => {
  assert.equal(topLevel.length, 153);
  assert.ok(topLevel.every((a) => !a.parent_slug));
});
