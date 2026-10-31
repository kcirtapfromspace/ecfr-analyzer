// End-to-end tests of the exported site. Export first (uv run ecfr export --out site), then: npm run e2e
import { defineConfig } from "@playwright/test";

const port = 8321;
const url = `http://127.0.0.1:${port}/ecfr-analyzer/`;

export default defineConfig({
  testDir: ".",
  timeout: 30_000,
  use: { baseURL: url, browserName: "chromium" },
  webServer: {
    command: `uv run python app/tests/e2e/serve.py site ${port}`,
    cwd: new URL("../../..", import.meta.url).pathname,
    url,
    reuseExistingServer: !process.env.CI,
  },
  reporter: [["list"]],
});
