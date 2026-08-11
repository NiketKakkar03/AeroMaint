import { expect, test } from "@playwright/test";

test("session library drives synchronized stereo media and timestamp deep links", async ({
  page
}) => {
  await page.goto("/sessions?fixture=1");
  const card = page.getByRole("button", {
    name: /Playable two-camera browser fixture/
  });
  await expect(card).toContainText("synthetic");
  await expect(card).toContainText("10.00 s");
  await expect(card).toContainText("2");
  await expect(card).toContainText("1.0.0");
  await expect(card).toContainText("ready");
  await card.click();
  await expect(page.getByTestId("camera-left-fixture-media")).toContainText(
    "LEFT"
  );
  await expect(page.getByTestId("camera-right-fixture-media")).toContainText(
    "RIGHT"
  );
  await page.getByLabel("Session timeline").fill("4500");
  await expect(page.getByText("Missing frames · missing")).toBeVisible();
  await expect(page).toHaveURL(/fixture=1.*t=9007203754740993/);
  await page.reload();
  await expect(page.getByText("Missing frames · missing")).toBeVisible();
  await page.getByRole("button", { name: "Play" }).click();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
});
