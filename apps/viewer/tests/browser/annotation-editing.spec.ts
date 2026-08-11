import { expect, test } from "@playwright/test";

test("creates, edits, reviews, and virtualizes point and interval annotations", async ({
  page
}) => {
  await page.goto("/sessions/synthetic-stereo?fixture=1");
  await expect(page.getByRole("region", { name: "Annotations" })).toBeVisible();
  await page.getByLabel("Annotation kind").fill("bearing noise");
  await page.getByRole("button", { name: "Add annotation" }).click();
  const point = page.getByRole("button", {
    name: /bearing noise point, draft, version 1/
  });
  await expect(point).toBeVisible();
  await point.click();
  await page.getByLabel("Annotation shape").selectOption("interval");
  await page.getByLabel("Annotation duration").fill("2");
  await page.getByRole("button", { name: "Save annotation" }).click();
  const interval = page.getByRole("button", {
    name: /bearing noise interval, draft, version 2/
  });
  await expect(interval).toBeVisible();
  await interval.click();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(
    page.getByRole("button", {
      name: /bearing noise interval, approved, version 3/
    })
  ).toBeVisible();
  await expect(page.locator('[data-virtualized-track="true"]')).toHaveCount(3);
});
