import { expect, test } from "@playwright/test";

test("empty API state renders the clean-install viewer path", async ({
  page
}) => {
  await page.route("**/v1/sessions", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: '{"items":[],"next_cursor":null}'
    })
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "No capture sessions" })
  ).toBeVisible();
  await expect(
    page.getByText("Import a session to begin inspection.")
  ).toBeVisible();
});
