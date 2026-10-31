---
title: eCFR Analyzer
---

# eCFR Analyzer

```js
import {filterRows, firstDirection, formatDecimal, formatInt, formatPercent, sortRows} from "./components/table.js";

const agencies = FileAttachment("data/agencies.json").json();
```

```js
// Words vs. restriction density; clicking a point opens that agency.
const scatter = Plot.plot({
  height: 280,
  x: {type: "log", label: "Words (log scale)"},
  y: {label: "Restriction terms per 1,000 words"},
  marks: [Plot.dot(agencies.filter((a) => !a.parent_slug && a.words >= 1000), {x: "words", y: "density", tip: true, title: "name"})]
});
scatter.addEventListener("click", () => scatter.value && select(scatter.value.slug));
display(html`<div data-testid="scatter">${scatter}</div>`);
```

```js
const search = view(html`<input type="search" data-testid="search" placeholder="Filter agencies (includes sub-agencies)">`);
```

```js
// Sort and selection state; the setters are used by the table cell below.
const sort = Mutable({key: "words", dir: "descending"});
const sortBy = (key) => {
  const {key: current, dir} = sort.value;
  sort.value = {key, dir: key === current ? (dir === "ascending" ? "descending" : "ascending") : firstDirection(key)};
};
const selected = Mutable(null);
const select = (slug) => (selected.value = slug);
```

```js
const columns = [["name", "Agency"], ["words", "Words"], ["density", "Restrictions / 1k"], ["stale_share", "Unchanged since 2017"], ["flagged_parts", "Flagged parts"]];
const rows = sortRows(filterRows(agencies, search), sort.key, sort.dir);
display(html`<table data-testid="agencies">
  <thead><tr>${columns.map(([key, label]) => html`<th data-sort=${key} aria-sort=${key === sort.key ? sort.dir : "none"} onclick=${() => sortBy(key)}>${label}</th>`)}</tr></thead>
  <tbody>${rows.map((a) => html`<tr data-slug=${a.slug} onclick=${() => select(a.slug)}>
    <td>${a.short_name ? `${a.name} (${a.short_name})` : a.name}</td>
    <td>${formatInt(a.words)}</td><td>${formatDecimal(a.density)}</td><td>${formatPercent(a.stale_share)}</td><td>${formatInt(a.flagged_parts)}</td>
  </tr>`)}</tbody>
</table>`);
```

```js
// Detail for the selected agency; the merged history file loads on first use.
const agency = agencies.find((a) => a.slug === selected);
if (agency) {
  const years = (await FileAttachment("data/history.json").json())[agency.slug];
  const long = years.flatMap((y) => ["substantive", "nonsubstantive", "removed"].map((type) => ({year: String(y.year), type, count: y[type]})));
  display(html`<section>
    <h2 data-testid="detail-name">${agency.name}</h2>
    <dl>
      <dt>Words</dt><dd data-testid="detail-words">${formatInt(agency.words)}</dd>
      <dt>Restrictions / 1k</dt><dd data-testid="detail-density">${formatDecimal(agency.density)}</dd>
    </dl>
    <div data-testid="history">${Plot.plot({height: 240, color: {legend: true}, x: {label: null}, y: {label: "Section changes"}, marks: [Plot.barY(long, {x: "year", y: "count", fill: "type"})]})}</div>
  </section>`);
}
```

<style>
th { cursor: pointer; user-select: none; text-align: right; }
th:first-child, td:first-child { text-align: left; }
td { text-align: right; font-variant-numeric: tabular-nums; }
th[aria-sort="ascending"]::after { content: " ▲"; }
th[aria-sort="descending"]::after { content: " ▼"; }
tbody tr { cursor: pointer; }
</style>
