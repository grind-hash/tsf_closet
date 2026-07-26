import { expect, test } from "@playwright/test";

test.describe("Action mode (US4)", () => {
  test("instruction type selector includes 'action' option", async ({
    page,
  }) => {
    await page.goto("/play");

    // Wait for the play screen to render
    await expect(page.locator(".game-play-screen")).toBeVisible();

    // Find the instruction type selector
    const selector = page.locator(".chat-input__type-select");
    await expect(selector).toBeVisible();

    // Verify that the "action" option exists in the selector
    const actionOption = selector.locator('option[value="action"]');
    await expect(actionOption).toBeAttached();

    // Verify the label text (Japanese locale default)
    const optionText = await actionOption.textContent();
    expect(optionText).toBeTruthy();
  });

  test("can select 'action' instruction type", async ({ page }) => {
    await page.goto("/play");

    await expect(page.locator(".game-play-screen")).toBeVisible();

    const selector = page.locator(".chat-input__type-select");
    await expect(selector).toBeVisible();

    // Select the action option
    await selector.selectOption("action");

    // Verify the selector now has the action value
    await expect(selector).toHaveValue("action");
  });

  test("all four instruction types are present in selector", async ({
    page,
  }) => {
    await page.goto("/play");

    await expect(page.locator(".game-play-screen")).toBeVisible();

    const selector = page.locator(".chat-input__type-select");
    await expect(selector).toBeVisible();

    const options = selector.locator("option");
    const count = await options.count();

    // Expect exactly 4 options: dress_up, reality_alter, conversation, action
    expect(count).toBe(4);

    const values: string[] = [];
    for (let i = 0; i < count; i++) {
      const val = await options.nth(i).getAttribute("value");
      if (val) values.push(val);
    }

    expect(values).toContain("dress_up");
    expect(values).toContain("reality_alter");
    expect(values).toContain("conversation");
    expect(values).toContain("action");
  });
});
