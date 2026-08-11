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
  const selectedUrl = page.url();
  await expect(page).toHaveURL(/fixture=1.*t=\d+/);
  await page.reload();
  expect(page.url()).toBe(selectedUrl);
  await expect(page.getByText("Missing frames · missing")).toBeVisible();
  await page.getByRole("button", { name: "Play" }).click();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
});
