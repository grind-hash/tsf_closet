import { expect, test } from "@playwright/test";

const APP_URL = "http://127.0.0.1:3000";
const SESSION_ID = "77777777-7777-4777-8777-777777777777";

test("衣装レイヤー設定を保存し右パネルへ同期する", async ({ page }) => {
  let capturedRespectClothingLayers: boolean | undefined;
  await page.addInitScript(() => {
    if (!window.sessionStorage.getItem("clothing_layer_test_initialized")) {
      window.localStorage.removeItem("app_settings");
      window.sessionStorage.setItem("clothing_layer_test_initialized", "true");
    }
    window.localStorage.setItem("novelai_api_key_consent", "true");
  });
  await page.route("**/api/game/characters", async (route) => {
    await route.fulfill({ status: 200, json: { characters: [] } });
  });
  await page.route("**/api/game/sessions/*/restore", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        session_id: SESSION_ID,
        character_id: "clothing-layer-character",
        current_image_url: null,
        transformation_count: 0,
        history: [],
        stats: {
          bloom: 0,
          shame: 0,
          adaptation: 0,
          nsfw_mode: false,
        },
        attributes: [],
        conversation_history: [],
      },
    });
  });
  await page.route("**/api/game/play/stream", async (route) => {
    const payload = route.request().postDataJSON() as
      | { respect_clothing_layers?: boolean }
      | undefined;
    capturedRespectClothingLayers = payload?.respect_clothing_layers;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        "event: text",
        'data: {"chunk":"確認"}',
        "",
        "event: complete",
        `data: {"session_id":"${SESSION_ID}","transformation_count":1}`,
        "",
      ].join("\n"),
    });
  });

  await page.goto(APP_URL);
  await page.locator(".backdrop").first().waitFor({ state: "hidden" });
  const closeError = page.getByRole("button", { name: /^(閉じる|Close)$/i });
  if (await closeError.isVisible()) {
    await closeError.click();
  }

  await page
    .getByRole("button", { name: /設定|Settings/i })
    .first()
    .click();

  const setting = page
    .locator(".settings-screen__item")
    .filter({ hasText: /衣装の重なりを考慮|Respect Clothing Layers/i });
  const settingsToggle = setting.getByRole("checkbox");
  await expect(settingsToggle).not.toBeChecked();
  await setting.locator("label").click();
  await expect(settingsToggle).toBeChecked();

  await expect
    .poll(() =>
      page.evaluate(() => {
        const raw = window.localStorage.getItem("app_settings");
        return raw ? JSON.parse(raw).respectClothingLayers : false;
      }),
    )
    .toBe(true);

  await page.reload();
  await page.locator(".backdrop").first().waitFor({ state: "hidden" });
  await page
    .getByRole("button", { name: /設定|Settings/i })
    .first()
    .click();
  await expect(
    page
      .locator(".settings-screen__item")
      .filter({ hasText: /衣装の重なりを考慮|Respect Clothing Layers/i })
      .getByRole("checkbox"),
  ).toBeChecked();

  await page.goto(`${APP_URL}/play/${SESSION_ID}`);
  await expect(page.locator(".game-play-screen")).toBeVisible();
  await page.getByRole("button", { name: /パネルを開く|Open panel/i }).click();

  const rightPanelSetting = page
    .locator(".right-panel__form-group")
    .filter({ hasText: /衣装の重なりを考慮|Respect Clothing Layers/i });
  await expect(rightPanelSetting.getByRole("checkbox")).toBeChecked();
  await expect(
    rightPanelSetting.getByText(/透ける素材|Explicit sheer fabric/i),
  ).toBeVisible();

  await page
    .getByRole("button", { name: /パネルを閉じる|Close panel/i })
    .first()
    .click();
  await page.locator(".chat-input__textarea").fill("外出着に着替える");
  await page.locator(".chat-input__send-btn").click();
  await expect.poll(() => capturedRespectClothingLayers).toBe(true);
});
