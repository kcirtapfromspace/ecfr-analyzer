// The exported site served under /ecfr-analyzer/, as on GitHub Pages. Expected values are read from the site's
// own JSON API, so the tests keep passing as the daily refresh changes the data.
import { expect, test } from "@playwright/test";

const fmt = (n) => n.toLocaleString("en-US");
/** Chart.js has drawn a chart on the canvas matching `selector`. */
const hasChart = (page, selector) => page.evaluate((s) => !!Chart.getChart(document.querySelector(s)), selector);

test("agency table: sort by clicking headers, search, open details", async ({ page, request }) => {
  const agencies = await (await request.get("api/agencies.json")).json();
  const top = agencies.filter((a) => !a.parent_slug);
  await page.goto("./");
  const table = page.locator("table:has(#rows)");
  const rows = page.locator("#rows tr:visible");
  const header = (label) => table.locator("thead th", { hasText: label });
  await expect(rows).toHaveCount(top.length);
  expect(await hasChart(page, "canvas[data-chart*='\"scatter\"']")).toBe(true);

  const byDensity = [...top].sort((a, b) => (b.density ?? -Infinity) - (a.density ?? -Infinity));
  await header("Restrictions / 1k").click();
  await expect(header("Restrictions / 1k")).toHaveAttribute("data-dir", "desc");
  await expect(rows.first()).toContainText(byDensity[0].name);
  await header("Restrictions / 1k").click();
  await expect(header("Restrictions / 1k")).toHaveAttribute("data-dir", "asc");
  const lowest = byDensity.at(-1); // nulls sort lowest, shown as "—"
  if (lowest.density == null) await expect(rows.first().locator("td").nth(2)).toHaveText("—");
  else await expect(rows.first()).toContainText(lowest.name);

  const byName = [...top].sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
  await header("Agency").click();
  await expect(header("Agency")).toHaveAttribute("data-dir", "asc");
  await expect(rows.first()).toContainText(byName[0].name);

  // Search covers sub-agencies, which are hidden until searched for.
  const child = agencies.find((a) => a.parent_slug);
  await page.locator("#q").fill(child.name);
  await expect(rows.filter({ hasText: child.name }).first()).toBeVisible();
  await page.locator("#q").fill("");
  await expect(rows).toHaveCount(top.length);

  const epa = agencies.find((a) => a.slug === "environmental-protection-agency");
  await page.locator("#q").fill(epa.name);
  await rows.filter({ hasText: epa.name }).first().click();
  const detail = page.locator("#detail");
  await expect(detail.locator("h2")).toHaveText(epa.name);
  await expect(detail.locator("dd").first()).toContainText(fmt(epa.words));
  await expect(detail.locator("dd").nth(1)).toContainText(`${epa.density.toFixed(1)} per 1,000 words`);
  await expect.poll(() => hasChart(page, "#detail canvas[data-chart*='\"history\"']")).toBe(true);
});

test("review candidates: filter by agency and sort", async ({ page, request }) => {
  const slug = "environmental-protection-agency";
  const epa = (await (await request.get(`api/candidates/${slug}.json`)).json()).candidates.slice(0, 25);
  await page.goto("./");
  await page.locator("select[name=agency]").selectOption(slug);
  const rows = page.locator("#candidates tbody tr");
  await expect(rows).toHaveCount(epa.length);
  await expect(rows.first().locator("td").nth(1)).toContainText(`${epa[0].title} CFR ${epa[0].part}`);

  const words = page.locator("#candidates thead th", { hasText: "Words" });
  await words.click();
  await expect(words).toHaveAttribute("data-dir", "desc");
  await expect(rows.first().locator("td").nth(2)).toHaveText(fmt(Math.max(...epa.map((c) => c.words))));
});
