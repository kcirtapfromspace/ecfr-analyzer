// The exported site served under /ecfr-analyzer/, as on GitHub Pages. Expected values are read from the site's
// own JSON API, so the tests keep passing as the daily refresh changes the data.
import { expect, test } from "@playwright/test";

const fmt = (n) => n.toLocaleString("en-US");
const agencyPath = (slug) => `agency/${encodeURIComponent(slug)}/`;
/** Chart.js has drawn a chart on the canvas matching `selector`. */
const hasChart = (page, selector) => page.evaluate((s) => !!Chart.getChart(document.querySelector(s)), selector);
const getJSON = async (request, path) => (await request.get(path)).json();

test("overview: sort and filter the agency table, open an agency, come back", async ({ page, request }) => {
  const agencies = await getJSON(request, "api/agencies.json");
  const top = agencies.filter((a) => !a.parent_slug);
  await page.goto("./");
  const table = page.locator("#agencies");
  const rows = table.locator("tbody tr:visible");
  const header = (label) => table.locator("thead th", { hasText: label });
  await expect(rows).toHaveCount(top.length);
  expect(await hasChart(page, "canvas[data-chart*='\"scatter\"']")).toBe(true);

  const byDensity = [...top].sort((a, b) => (b.density ?? -Infinity) - (a.density ?? -Infinity));
  await header("Restriction density").click();
  await expect(header("Restriction density")).toHaveAttribute("data-dir", "desc");
  await expect(rows.first()).toContainText(byDensity[0].name);
  await header("Restriction density").click();
  await expect(header("Restriction density")).toHaveAttribute("data-dir", "asc");
  const lowest = byDensity.at(-1); // nulls sort lowest, shown as "—"
  if (lowest.density == null) await expect(rows.first().locator("td").nth(2)).toHaveText("—");
  else await expect(rows.first()).toContainText(lowest.name);

  const byName = [...top].sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
  await header("Agency").click();
  await expect(header("Agency")).toHaveAttribute("data-dir", "asc");
  await expect(rows.first()).toContainText(byName[0].name);

  // The filter covers sub-agencies, which stay hidden until searched for.
  const child = agencies.find((a) => a.parent_slug);
  await page.locator("#q").fill(child.name);
  await expect(rows.filter({ hasText: child.name }).first()).toBeVisible();

  const epa = agencies.find((a) => a.slug === "environmental-protection-agency");
  await page.locator("#q").fill(epa.name);
  await rows.filter({ hasText: epa.name }).first().click(); // the row's middle, not the link text
  await expect(page).toHaveURL(new RegExp(`/${agencyPath(epa.slug)}$`));
  await expect(page.locator("h1")).toContainText(epa.name);
  await expect(page.locator(".cards")).toContainText(fmt(epa.words));
  await expect(page.locator(".cards")).toContainText(epa.density.toFixed(1));
  await expect.poll(() => hasChart(page, "canvas[data-chart*='\"history\"']")).toBe(true);
  await page.goBack();
  await expect(page).toHaveURL(/\/ecfr-analyzer\/$/);
});

test("agency page: breadcrumb, sub-agencies and review candidates", async ({ page, request }) => {
  const agencies = await getJSON(request, "api/agencies.json");
  const child = agencies.find((a) => a.parent_slug);
  const parent = agencies.find((a) => a.slug === child.parent_slug);
  await page.goto(agencyPath(child.slug));
  await expect(page.locator("h1")).toContainText(child.name);
  const crumbs = page.locator(".crumbs");
  await expect(crumbs).toContainText("Overview");
  await crumbs.getByRole("link", { name: parent.name }).click();
  await expect(page.locator("h1")).toContainText(parent.name);
  await expect(page.getByRole("link", { name: child.name })).toBeVisible();

  const slug = "environmental-protection-agency";
  const epa = (await getJSON(request, `api/candidates/${slug}.json`)).candidates.slice(0, 25);
  await page.goto(agencyPath(slug));
  const rows = page.locator("#candidates tbody tr");
  await expect(rows).toHaveCount(epa.length);
  await expect(rows.first()).toContainText(`${epa[0].title} CFR ${epa[0].part}`);
  const words = page.locator("#candidates thead th", { hasText: "Words" });
  await words.click();
  await expect(words).toHaveAttribute("data-dir", "desc");
  await expect(rows.first().locator("td").nth(2)).toHaveText(fmt(Math.max(...epa.map((c) => c.words))));
});

test("the header search finds agencies from any page", async ({ page, request }) => {
  const q = "environmental protection";
  const hits = (await getJSON(request, "api/agencies.json")).filter((a) => `${a.name} ${a.short_name ?? ""}`.toLowerCase().includes(q));
  await page.goto("explore/");
  await page.locator("#q").fill(q);
  await page.locator("#q").press("Enter");
  await expect(page).toHaveURL(/\/ecfr-analyzer\/\?q=environmental\+protection$/);
  const rows = page.locator("#agencies tbody tr:visible");
  await expect(rows).toHaveCount(hits.length);
  await rows.filter({ hasText: "Environmental Protection Agency" }).click();
  await expect(page).toHaveURL(/\/agency\/environmental-protection-agency\/$/);
});

test("every same-site link and asset resolves under the subpath", async ({ page, request }) => {
  const agencies = await getJSON(request, "api/agencies.json");
  const odd = agencies.find((a) => /[',()]/.test(a.slug)); // slugs with ' ( ) , must survive URL encoding
  for (const path of ["./", "explore/", agencyPath("environmental-protection-agency"), agencyPath(odd.slug)]) {
    await page.goto(path);
    await expect(page.locator("h1")).toHaveCount(1);
    const urls = await page.$$eval("a[href], link[href], script[src]", (els) =>
      els.map((e) => e.href || e.src).filter((u) => u.startsWith(location.origin)));
    for (const url of new Set(urls)) expect((await request.get(url)).status(), url).toBe(200);
  }
  await page.reload(); // a nested page reloads with working charts
  await expect.poll(() => hasChart(page, "canvas[data-chart*='\"history\"']")).toBe(true);
});

test("explore: a SQL query runs in the browser over the Parquet files", async ({ page }) => {
  test.setTimeout(90_000); // the first run downloads DuckDB-WASM from the CDN
  await page.goto("explore/");
  await page.locator("#run").click();
  await expect(page.locator("#status")).toContainText("rows in", { timeout: 80_000 });
  await expect(page.locator("#result tbody tr").first()).toBeVisible();
});
