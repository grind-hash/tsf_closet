import { expect, test } from "@playwright/test";

const APP_URL = "http://127.0.0.1:3000";
const SESSION_ID = "88888888-8888-4888-8888-888888888888";

test("保持する要素セクションに削除予定の案内を表示しつつ機能は維持する", async ({
  page,
}) => {
  let capturedPreserveElements: string[] | undefined;
  await page.addInitScript(() => {
    if (!window.sessionStorage.getItem("preserve_deprecation_initialized")) {
      window.localStorage.removeItem("app_settings");
      window.sessionStorage.setItem("preserve_deprecation_initialized", "true");
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
        character_id: "preserve-deprecation-character",
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
      | { preserve_elements?: string[] }
      | undefined;
    capturedPreserveElements = payload?.preserve_elements;
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

  await page.goto(`${APP_URL}/play/${SESSION_ID}`);
  await expect(page.locator(".game-play-screen")).toBeVisible();
  const closeError = page.getByRole("button", { name: /^(閉じる|Close)$/i });
  if (await closeError.isVisible()) {
    await closeError.click();
  }
  await page.getByRole("button", { name: /パネルを開く|Open panel/i }).click();

  const preserveSection = page
    .locator(".right-panel__section")
    .filter({ hasText: /保持する要素|Preserve Elements/i })
    .first();

  // Deprecated チップがセクション見出しに表示される
  const chip = preserveSection.locator(".feature-chip-deprecated");
  await expect(chip).toBeVisible();
  await expect(chip).toHaveText("Deprecated");
  await expect(chip).toHaveAttribute("data-removal-version", "v0.8.0");
  await expect(chip).toHaveAttribute("title", /v0\.8\.0/);
  await expect(chip).toHaveAttribute("title", /ユーザーメモ|User Memory/i);

  // ツールチップに加えて常時表示の案内も出す
  const notice = preserveSection.locator(".right-panel__hint--deprecated");
  await expect(notice).toBeVisible();
  await expect(notice).toContainText(/v0\.8\.0/);
  await expect(notice).toContainText(/ユーザーメモ|User Memory/i);

  // v0.7.0 時点では機能自体は従来どおり動作する
  const backgroundCheckbox = preserveSection
    .locator(".right-panel__checkbox")
    .filter({ hasText: /背景を保持する|Preserve background/i })
    .getByRole("checkbox");
  await expect(backgroundCheckbox).not.toBeChecked();
  await backgroundCheckbox.check();
  await expect(backgroundCheckbox).toBeChecked();

  await page
    .getByRole("button", { name: /パネルを閉じる|Close panel/i })
    .first()
    .click();
  await page.locator(".chat-input__textarea").fill("外出着に着替える");
  await page.locator(".chat-input__send-btn").click();
  await expect.poll(() => capturedPreserveElements).toContain("background");
});
