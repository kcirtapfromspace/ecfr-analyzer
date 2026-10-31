// The same end-to-end test for every candidate (see frontends/CONTRACT.md).
import { test, expect } from "@playwright/test";

test("sort, search and open an agency", async ({ page }) => {
  await page.goto("./");
  const table = page.getByTestId("agencies");
  const rows = table.locator("tbody tr:visible");
  const header = (key) => table.locator(`th[data-sort=${key}]`);

  await expect(rows).toHaveCount(153);
  await expect(page.getByTestId("scatter")).toBeVisible();

  await header("density").click();
  await expect(header("density")).toHaveAttribute("aria-sort", "descending");
  await expect(rows.first()).toContainText("Architectural and Transportation Barriers Compliance Board");
  await header("density").click();
  await expect(header("density")).toHaveAttribute("aria-sort", "ascending");

  await header("name").click();
  await expect(header("name")).toHaveAttribute("aria-sort", "ascending");
  await expect(rows.first()).toContainText("Administrative Committee of the Federal Register");

  await page.getByTestId("search").fill("occupational");
  await expect(rows).toHaveCount(2);
  await page.getByTestId("search").fill("environmental protection agency");
  await table.locator("tr[data-slug=environmental-protection-agency]").click();

  await expect(page.getByTestId("detail-name")).toHaveText("Environmental Protection Agency");
  await expect(page.getByTestId("detail-words")).toHaveText("18,133,322");
  await expect(page.getByTestId("detail-density")).toHaveText("10.3");
  await expect(page.getByTestId("history")).toBeVisible();
});
