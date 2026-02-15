import { test, expect } from "@playwright/test";

test("inpaint OFF clears mask configured state", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
  });
  await page.goto("http://localhost:3000/play");

  await page.locator(".backdrop").first().waitFor({ state: "hidden" });
  await page.getByText("🎨 インペイントモード").click();

  const applyButton = page.getByRole("button", { name: "適用" });
  if (!(await applyButton.isVisible().catch(() => false))) {
    await page.getByRole("button", { name: "✂️ マスク編集" }).click();
  }
  await page.getByRole("button", { name: "適用" }).click();

  await expect(page.getByText("✓ マスクが設定されています")).toBeVisible();

  await page.getByText("🎨 インペイントモード").click();
  await expect(page.getByText("✓ マスクが設定されています")).toBeHidden();
});
