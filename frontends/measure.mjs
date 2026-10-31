// Measure what each candidate ships: load the index under /ecfr-analyzer/, then open EPA's detail.
// Usage: node measure.mjs name=url [name=url ...]   (url = http://127.0.0.1:PORT/ecfr-analyzer/)
import { gzipSync } from "node:zlib";
import { chromium } from "@playwright/test";

const BUCKETS = [
  ["chart library", /chart\.umd|\/chart[-.][\w-]*\.js|@observablehq\/plot|_npm\/(d3-|internmap|delaunator|robust-predicates|binary-search-bounds|interval-tree)/],
  ["framework runtime", /htmx\.min\.js|_observablehq\/|_npm\/(htl|@observablehq)|\/_app\/immutable\/(chunks|entry)\//],
  ["data", /\/api\/|\/ui\/|__data\.json|_file\/|\/agency\/[^/]+\.html$/],
  ["fonts", /fonts\.(googleapis|gstatic)\.com/],
  ["app code", /\.(js|mjs)(\?|$)/],
  ["html + css", /./],
];
const bucketOf = (url) => BUCKETS.find(([, re]) => re.test(url))[0];

async function capture(page, action) {
  const seen = [];
  const onResponse = async (r) => {
    try {
      const body = await r.body();
      const type = r.headers()["content-type"] ?? "";
      const compressible = !/woff2?|png|jpe?g|parquet/.test(type + r.url());
      seen.push({ url: r.url(), bytes: body.length, gzip: compressible ? gzipSync(body, { level: 9 }).length : body.length });
    } catch {
      /* redirects and aborted requests have no body */
    }
  };
  page.on("response", onResponse);
  await action();
  await page.waitForLoadState("networkidle");
  page.off("response", onResponse);
  const totals = {};
  for (const r of seen) {
    const b = (totals[bucketOf(r.url)] ??= { requests: 0, bytes: 0, gzip: 0 });
    b.requests += 1; b.bytes += r.bytes; b.gzip += r.gzip;
  }
  return totals;
}

const browser = await chromium.launch();
const results = {};
for (const arg of process.argv.slice(2)) {
  const [name, url] = arg.split("=");
  const page = await browser.newPage();
  const started = Date.now();
  const index = await capture(page, async () => {
    await page.goto(url);
    await page.locator('[data-testid=agencies] tbody tr').first().waitFor();
  });
  const firstView = Date.now() - started;
  const detail = await capture(page, async () => {
    await page.getByTestId("search").fill("environmental protection agency");
    await page.locator("tr[data-slug=environmental-protection-agency]").click();
    await page.getByTestId("detail-name").waitFor();
  });
  results[name] = { index, detail, firstViewMs: firstView };
  await page.close();
}
await browser.close();
console.log(JSON.stringify(results, null, 1));
