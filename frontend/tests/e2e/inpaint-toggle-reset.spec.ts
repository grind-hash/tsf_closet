import { test, expect } from "@playwright/test";
import { startFirstCharacterGame } from "./helpers/gameplay";

test("inpaint OFF clears mask configured state", async ({ page }) => {
  // Intercept health endpoint to ensure image_provider is "novelai"
  await page.route("**/health", async (route) => {
    const response = await route.fetch();
    const json = await response.json();
    json.image_provider = "novelai";
    await route.fulfill({ response, json });
  });

  await startFirstCharacterGame(page);

  // Language-agnostic locator for inpaint toggle
  const inpaintToggle = page.getByText(/インペイントモード|Inpaint Mode/);
  await expect(inpaintToggle).toBeVisible({ timeout: 10_000 });
  await inpaintToggle.click();

  // Language-agnostic locators for buttons and status
  const applyButton = page.getByRole("button", { name: /適用|Apply/ });
  const maskEditButton = page.getByRole("button", {
    name: /マスク編集|Edit Mask/,
  });
  if (!(await applyButton.isVisible().catch(() => false))) {
    await maskEditButton.click();
  }
  await applyButton.click();

  const maskStatus = page.getByText(
    /マスクが設定されています|Mask is configured/,
  );
  await expect(maskStatus).toBeVisible();

  await inpaintToggle.click();
  await expect(maskStatus).toBeHidden();
});
