import { expect, test } from "@playwright/test";

const APP_URL = "http://127.0.0.1:3000";

test("プレイメモを有効化すると右パネルに専用欄を表示する", async ({ page }) => {
  await page.addInitScript(() => {
    if (!window.sessionStorage.getItem("play_memory_test_initialized")) {
      window.localStorage.removeItem("app_settings");
      window.sessionStorage.setItem("play_memory_test_initialized", "true");
    }
    window.localStorage.setItem("novelai_api_key_consent", "true");
  });
  await page.route("**/api/game/characters", async (route) => {
    await route.fulfill({ status: 200, json: { characters: [] } });
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

  const experimentalSection = page
    .locator(".settings-screen__section")
    .filter({ has: page.getByRole("heading", { name: /Experimental/i }) });
  const setting = experimentalSection
    .locator(".settings-screen__item")
    .filter({ hasText: /プレイメモ|Play Memory/i });
  const toggle = setting.getByRole("checkbox");
  await expect(toggle).not.toBeChecked();
  await setting.locator("label").click();
  await expect(toggle).toBeChecked();
  await expect
    .poll(() =>
      page.evaluate(() => {
        const raw = window.localStorage.getItem("app_settings");
        return raw ? JSON.parse(raw).playMemoryEnabled : false;
      }),
    )
    .toBe(true);

  await page.goto(`${APP_URL}/play`);
  await page.getByRole("button", { name: /パネルを開く|Open panel/i }).click();

  await expect(
    page.getByRole("heading", { name: /プレイメモ|Play Memory/i }),
  ).toBeVisible();
  await expect(page.getByText(/^(自動メモ|Automatic Memory)$/i)).toBeVisible();
  await expect(page.getByText(/^(ユーザーメモ|User Memory)$/i)).toBeVisible();
  const textareas = page.locator(".play-memory__textarea");
  await expect(textareas).toHaveCount(2);
  await expect(textareas.first()).toHaveClass(/right-panel__textarea/);
  await expect(textareas.first()).toHaveAttribute("rows", "5");
  await expect(textareas.last()).toHaveAttribute("rows", "5");
  await expect(
    page.getByRole("button", {
      name: /自動メモを再生成|Regenerate Automatic/i,
    }),
  ).toHaveClass(/right-panel__btn-primary/);
  await expect(
    page.getByRole("button", {
      name: /ユーザーメモを保存|Save User Memory/i,
    }),
  ).toHaveClass(/right-panel__btn-primary/);
});
