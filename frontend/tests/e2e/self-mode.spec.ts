import { test, expect } from "@playwright/test";

test.describe("Self mode (US5)", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("novelai_api_key_consent", "true");
    });
  });

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

  // FIXME: Provider detection may redirect away from welcome screen when active session exists
  test.fixme("self mode toggle can be checked and unchecked", async ({
    page,
  }) => {
    await page.goto("/");

    // Wait for any loading backdrops to disappear
    await page
      .locator(".backdrop")
      .first()
      .waitFor({ state: "hidden", timeout: 10_000 })
      .catch(() => {});

    // Wait for welcome screen to become stable after provider detection
    await expect(page.locator(".welcome-screen")).toBeVisible({
      timeout: 10_000,
    });

    // Click the label to toggle the controlled checkbox
    const label = page.locator(".welcome-screen__self-mode-label");
    const checkbox = page.locator(".welcome-screen__self-mode-checkbox");
    await expect(label).toBeVisible({ timeout: 5_000 });

    // Check via label click
    await label.click();
    await expect(checkbox).toBeChecked();

    // Uncheck via label click
    await label.click();
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
