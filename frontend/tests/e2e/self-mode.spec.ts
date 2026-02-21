import { test, expect } from "@playwright/test";

test.describe("Self mode (US5)", () => {
  test("self mode toggle is visible on welcome screen", async ({ page }) => {
    await page.goto("/");

    // Wait for the welcome screen to render
    await expect(page.locator(".welcome-screen")).toBeVisible();

    // Find the self-mode section
    const selfModeSection = page.locator(".welcome-screen__self-mode");
    await expect(selfModeSection).toBeVisible();

    // Find the checkbox
    const checkbox = selfModeSection.locator(
      'input[type="checkbox"].welcome-screen__self-mode-checkbox',
    );
    await expect(checkbox).toBeVisible();

    // Should be unchecked by default
    await expect(checkbox).not.toBeChecked();
  });

  test("self mode toggle can be checked and unchecked", async ({ page }) => {
    await page.goto("/");

    await expect(page.locator(".welcome-screen")).toBeVisible();

    const checkbox = page.locator(".welcome-screen__self-mode-checkbox");
    await expect(checkbox).toBeVisible();

    // Check the checkbox
    await checkbox.check();
    await expect(checkbox).toBeChecked();

    // Uncheck
    await checkbox.uncheck();
    await expect(checkbox).not.toBeChecked();
  });

  test("self mode label and description are displayed", async ({ page }) => {
    await page.goto("/");

    await expect(page.locator(".welcome-screen")).toBeVisible();

    const selfModeSection = page.locator(".welcome-screen__self-mode");

    // Check label text exists
    const label = selfModeSection.locator(
      ".welcome-screen__self-mode-label span",
    );
    const labelText = await label.textContent();
    expect(labelText).toBeTruthy();

    // Check description text exists
    const desc = selfModeSection.locator(".welcome-screen__self-mode-desc");
    const descText = await desc.textContent();
    expect(descText).toBeTruthy();
  });
});
