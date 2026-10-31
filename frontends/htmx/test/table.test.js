import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { compare, sortValue, visible } from "../static/table.js";

const agencies = JSON.parse(readFileSync(new URL("../../fixtures/api/agencies.json", import.meta.url), "utf8"));
// What templates/index.html writes into each row's data-v cells and data-search attribute.
const cell = (a, key) => (key === "name" ? a.name.toLowerCase() : a[key] == null ? "" : String(a[key]));
const haystack = (a) => `${a.name} ${a.short_name ?? ""}`.toLowerCase();
const sorted = (rows, key, dir) => [...rows].sort((a, b) => compare(sortValue(key, cell(a, key)), sortValue(key, cell(b, key)), dir));
const shown = (query) => agencies.filter((a) => visible(haystack(a), Boolean(a.parent_slug), query));
const topLevel = shown("");

test("density descending puts the Access Board first", () => {
  assert.equal(sorted(topLevel, "density", "descending")[0].name, "Architectural and Transportation Barriers Compliance Board");
});

test("nulls go last when descending", () => {
  const rows = sorted(agencies, "density", "descending");
  const firstNull = rows.findIndex((a) => a.density === null);
  assert.ok(firstNull > 0);
  assert.ok(rows.slice(firstNull).every((a) => a.density === null));
});

test("name ascending is case-insensitive", () => {
  assert.equal(sorted(topLevel, "name", "ascending")[0].name, "Administrative Committee of the Federal Register");
});

test("search spans sub-agencies", () => {
  const hits = shown("Occupational");
  assert.equal(hits.length, 2);
  assert.ok(hits.some((a) => a.parent_slug));
});

test("an empty query shows only top-level agencies", () => {
  assert.equal(topLevel.length, 153);
});
