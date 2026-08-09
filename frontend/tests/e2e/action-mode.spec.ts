import { expect, type Page, test } from "@playwright/test";

const sessionId = "33333333-3333-4333-8333-333333333333";

async function mockActiveSession(page: Page) {
  await page.route("**/api/game/characters", async (route) => {
    await route.fulfill({ status: 200, json: { characters: [] } });
  });
  await page.route("**/api/game/anlas", async (route) => {
    await route.fulfill({
      status: 200,
      json: { total_anlas: 0, fixed_anlas: 0, purchased_anlas: 0 },
    });
  });
  await page.route("**/api/game/sessions/*/restore", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        session_id: sessionId,
        character_id: "selector-test-character",
        current_image_url: null,
        transformation_count: 0,
        history: [],
        stats: { bloom: 0, shame: 0, adaptation: 0, nsfw_mode: false },
        attributes: [],
        conversation_history: [],
      },
    });
  });
}

test.describe("Action mode (US4)", () => {
  test.beforeEach(async ({ page }) => {
    await mockActiveSession(page);
  });

  test("instruction type selector includes 'action' option", async ({
    page,
  }) => {
    await page.goto(`/play/${sessionId}`);

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
    await page.goto(`/play/${sessionId}`);

    await expect(page.locator(".game-play-screen")).toBeVisible();

    const selector = page.locator(".chat-input__type-select");
    await expect(selector).toBeVisible();

    // Select the action option
    await selector.selectOption("action");

    // Verify the selector now has the action value
    await expect(selector).toHaveValue("action");
  });

  test("all five instruction types are present in selector", async ({
    page,
  }) => {
    await page.goto(`/play/${sessionId}`);

    await expect(page.locator(".game-play-screen")).toBeVisible();

    const selector = page.locator(".chat-input__type-select");
    await expect(selector).toBeVisible();

    const options = selector.locator("option");
    const count = await options.count();

    // 既存4種と実験的な画像のみを表示する
    expect(count).toBe(5);

    const values: string[] = [];
    for (let i = 0; i < count; i++) {
      const val = await options.nth(i).getAttribute("value");
      if (val) values.push(val);
    }

    expect(values).toContain("dress_up");
    expect(values).toContain("reality_alter");
    expect(values).toContain("conversation");
    expect(values).toContain("action");
    expect(values).toContain("image_only");
    await expect(selector.locator('option[value="image_only"]')).toContainText(
      "実験的",
    );
  });
});
