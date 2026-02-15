import { test, expect } from "@playwright/test";

test("language switch updates key labels", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
  });
  await page.goto("http://localhost:3000/play");

  await page.locator(".backdrop").first().waitFor({ state: "hidden" });

  await page.getByRole("button", { name: /パネルを開く|Open panel/i }).click();
  await page.getByRole("radio", { name: "English" }).check();
  await expect(page.getByText("Language: English")).toBeVisible();

  await page.getByRole("radio", { name: /日本語|Japanese/i }).check();
  await expect(page.getByText(/言語: 日本語|Language: Japanese/)).toBeVisible();
});
