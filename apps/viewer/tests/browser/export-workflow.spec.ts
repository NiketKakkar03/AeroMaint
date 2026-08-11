import { expect, test } from "@playwright/test";

test("creates a synchronized half-open export and exposes its manifest", async ({ page }) => {
  await page.goto("/sessions/synthetic-stereo?fixture=1");
  const panel = page.getByRole("region", { name: "Export synchronized range" });
  await expect(panel).toBeVisible();
  await page.getByLabel("Sensor export format").selectOption("json");
  await page.getByRole("button", { name: "Create export" }).click();
  await expect(page.getByRole("status")).toContainText("Export succeeded");
  await expect(page.getByRole("link", { name: "Download manifest" })).toBeVisible();
});
