import { expect, test } from "@playwright/test";

test("copilot recommendation stays draft until engineer approval", async ({
  page
}) => {
  await page.goto("/sessions/browser-stereo?fixture=1");
  await expect(
    page.getByRole("heading", { name: "Inspection copilot" })
  ).toBeVisible();
  await page
    .getByLabel("Ask about this session")
    .fill("What is the engine health?");
  await page.getByRole("button", { name: "Generate draft" }).click();
  await expect(
    page
      .getByText("Draft only: authorized engineer inspection required.")
      .first()
  ).toBeVisible();
  await page.getByRole("button", { name: "Approve recommendation" }).click();
  await expect(
    page.locator('.copilot-answer[data-status="approved"]')
  ).toBeVisible();
  await expect(page.getByText("No drafts awaiting review.")).toBeVisible();
});
