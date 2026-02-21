import { test, expect } from "@playwright/test";

test.describe("Self Profile Editor (US6)", () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to settings page
    await page.goto("/");
    // Open menu and navigate to settings
    const menuButton = page.locator('[class*="menu"]').first();
    if (await menuButton.isVisible()) {
      await menuButton.click();
    }
    // Try navigating directly to settings
    await page.goto("/#/settings");
    await page.waitForLoadState("networkidle");
  });

  test("self profile section is visible in settings", async ({ page }) => {
    // The self profile section title should be visible
    const sectionTitles = page.locator(".settings-screen__section-title");
    const titles = await sectionTitles.allTextContents();
    const hasSelfProfile = titles.some(
      (t) => t.includes("自分自身プロフィール") || t.includes("Self Profile"),
    );
    expect(hasSelfProfile).toBeTruthy();
  });

  test("self profile editor has generate input and button", async ({
    page,
  }) => {
    // Find the self-profile editor component
    const editor = page.locator(".self-profile-editor");
    await expect(editor).toBeVisible();

    // Check textarea exists
    const textarea = editor.locator(".self-profile-editor__textarea").first();
    await expect(textarea).toBeVisible();

    // Check generate button exists
    const generateBtn = editor.locator(".self-profile-editor__generate-btn");
    await expect(generateBtn).toBeVisible();

    // Generate button should be disabled when textarea is empty
    await expect(generateBtn).toBeDisabled();
  });

  test("generate button becomes enabled when text is entered", async ({
    page,
  }) => {
    const editor = page.locator(".self-profile-editor");
    const textarea = editor.locator(".self-profile-editor__textarea").first();
    const generateBtn = editor.locator(".self-profile-editor__generate-btn");

    // Initially disabled
    await expect(generateBtn).toBeDisabled();

    // Type some text
    await textarea.fill("20代の大学生でアニメが好き");

    // Button should now be enabled
    await expect(generateBtn).toBeEnabled();
  });

  test("clearing text disables generate button again", async ({ page }) => {
    const editor = page.locator(".self-profile-editor");
    const textarea = editor.locator(".self-profile-editor__textarea").first();
    const generateBtn = editor.locator(".self-profile-editor__generate-btn");

    // Type text
    await textarea.fill("test input");
    await expect(generateBtn).toBeEnabled();

    // Clear text
    await textarea.fill("");
    await expect(generateBtn).toBeDisabled();
  });
});
