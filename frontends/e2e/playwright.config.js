// Run with BASE_URL pointing at a candidate served under /ecfr-analyzer/, e.g.
//   BASE_URL=http://127.0.0.1:8401/ecfr-analyzer/ npx playwright test --config e2e/playwright.config.js
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 30_000,
  use: { baseURL: process.env.BASE_URL, browserName: "chromium" },
  reporter: [["list"]],
});
