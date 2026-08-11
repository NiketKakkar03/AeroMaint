import { expect, test } from "@playwright/test";

test("session library drives synchronized stereo media and timestamp deep links", async ({
  page
}, testInfo) => {
  await page.goto("/sessions?fixture=1");
  const card = page.getByRole("button", {
    name: /Playable two-camera browser fixture/
  });
  await expect(card).toContainText("synthetic");
  await expect(card).toContainText("10.00 s");
  await expect(card).toContainText("4");
  await expect(card).toContainText("1.0.0");
  await expect(card).toContainText("ready");
  await card.click();
  await expect(page.getByTestId("camera-left-fixture-media")).toContainText(
    "LEFT"
  );
  await expect(page.getByTestId("camera-right-fixture-media")).toContainText(
    "RIGHT"
  );
  await expect(page.getByRole("heading", { name: "imu-main" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "pose-main" })).toBeVisible();
  await expect(page.getByText("Data: raw")).toHaveCount(2);
  await page.getByLabel("Playback rate").selectOption("2");
  await expect(page.getByLabel("Playback rate")).toHaveValue("2");
  await page.getByRole("button", { name: "Zoom in timeline" }).click();
  await expect(page.getByLabel("Timeline zoom")).toHaveText("2×");
  await page.getByRole("button", { name: "Zoom in timeline" }).click();
  await page.getByRole("button", { name: "Zoom out timeline" }).click();
  await expect
    .poll(() =>
      page.evaluate(() => window.__AEROMAINT_FIXTURE_REQUESTS__?.aborted ?? 0)
    )
    .toBeGreaterThan(0);
  await page.getByLabel("Loop visible window").check();
  await expect(page.getByLabel("Loop visible window")).toBeChecked();
  const timeline = page.getByRole("slider", {
    name: "Session timeline",
    exact: true
  });
  await timeline.evaluate((element) => {
    const input = element as HTMLInputElement & {
      _valueTracker?: { setValue: (value: string) => void };
    };
    const previous = input.value;
    Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value"
    )?.set?.call(input, "4500");
    input._valueTracker?.setValue(previous);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await expect
    .poll(async () => Number(await timeline.inputValue()))
    .toBeGreaterThanOrEqual(4_000);
  await expect
    .poll(async () => Number(await timeline.inputValue()))
    .toBeLessThanOrEqual(5_000);
  await expect(page.getByText("Missing frames · missing")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("gap-state.png") });
  const selectedUrl = page.url();
  await expect(page).toHaveURL(/fixture=1.*t=\d+/);
  await page.reload();
  expect(page.url()).toBe(selectedUrl);
  await expect(page.getByText("Missing frames · missing")).toBeVisible();
  await page.getByRole("button", { name: "Play" }).click();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
  const duplicateIds = await page.locator("[id]").evaluateAll((elements) => {
    const counts = new Map<string, number>();
    for (const element of elements)
      counts.set(element.id, (counts.get(element.id) ?? 0) + 1);
    return [...counts.entries()].filter(([, count]) => count > 1);
  });
  expect(duplicateIds).toEqual([]);
});
