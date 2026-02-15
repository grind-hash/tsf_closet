import { test, expect } from "@playwright/test";

test("core flow smoke: play screen renders with chat input", async ({
  page,
}) => {
  await page.goto("http://localhost:3000/play");

  await expect(page.locator(".game-play-screen")).toBeVisible();
  await expect(
    page.locator("textarea, input[type='text']").first(),
  ).toBeVisible();
});
