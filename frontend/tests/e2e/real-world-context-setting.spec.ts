import { expect, test } from "@playwright/test";

const APP_URL = "http://127.0.0.1:3000";

const BASE_USER_SETTINGS = {
  nsfw_mode: false,
  difficulty: "normal",
  bloom_calc_method: "legacy",
  feeling_mode: "legacy",
  gender_congruence_llm_enabled: false,
  language: "ja",
  novelai_text_model: "glm-4-6",
  novelai_image_model: "nai-diffusion-4-5-full",
  novelai_curated_image_model: "nai-diffusion-4-5-curated",
  tts_enabled: false,
  tts_use_gpu: false,
  tts_engine_dir: null,
  tts_engine_port: null,
  tts_model_dir: null,
  tts_speaker_id: null,
  tts_style_id: null,
  tts_output_format: "wav",
  real_world_weather_enabled: false,
  real_world_search_enabled: false,
  prompt_preview_enabled: false,
  weather_configured: false,
  web_search_configured: false,
};

async function openSettings(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
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
  return page
    .locator(".settings-screen__section")
    .filter({ has: page.getByRole("heading", { name: /Experimental/i }) });
}

test("現実世界コンテキストの設定はデバッグモードが無効でも操作でき、理由を表示する", async ({
  page,
}) => {
  const putBodies: Record<string, unknown>[] = [];
  await page.route("**/api/settings/user", async (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      putBodies.push(body);
      await route.fulfill({
        status: 200,
        json: { ...BASE_USER_SETTINGS, ...body },
      });
      return;
    }
    await route.fulfill({ status: 200, json: BASE_USER_SETTINGS });
  });

  const experimentalSection = await openSettings(page);
  const weatherItem = experimentalSection
    .locator(".settings-screen__item")
    .filter({ hasText: /現実の日時と天気|Real-world date and weather/i });
  await expect(weatherItem).toBeVisible();
  await expect(
    weatherItem.locator(".settings-screen__item-note"),
  ).toContainText(/ENABLE_PROMPT_PREVIEW/);

  const toggle = weatherItem.getByRole("checkbox");
  await expect(toggle).not.toBeChecked();
  await weatherItem.locator("label").click();
  await expect(toggle).toBeChecked();
  await expect
    .poll(() =>
      putBodies.some((body) => body.real_world_weather_enabled === true),
    )
    .toBe(true);
});

test("設定済みの項目は通常説明、未設定の項目は環境変数名を表示する", async ({
  page,
}) => {
  await page.route("**/api/settings/user", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        ...BASE_USER_SETTINGS,
        prompt_preview_enabled: true,
        weather_configured: true,
        web_search_configured: false,
      },
    });
  });

  const experimentalSection = await openSettings(page);
  const weatherItem = experimentalSection
    .locator(".settings-screen__item")
    .filter({ hasText: /現実の日時と天気|Real-world date and weather/i });
  // 設定済みなら「効かない理由」の注記は出ない(説明文は残る)
  await expect(weatherItem).toBeVisible();
  await expect(weatherItem.locator(".settings-screen__item-note")).toHaveCount(
    0,
  );

  const searchItem = experimentalSection
    .locator(".settings-screen__item")
    .filter({ hasText: /Web検索で調べる|Look things up on the web/i });
  await expect(searchItem.locator(".settings-screen__item-note")).toContainText(
    /TAVILY_API_KEY/,
  );
});

async function openGuide(
  page: import("@playwright/test").Page,
  settings: Record<string, unknown>,
) {
  await page.addInitScript(() => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
  });
  await page.route("**/api/settings/user", async (route) => {
    await route.fulfill({ status: 200, json: settings });
  });
  await page.goto(`${APP_URL}/guide`);
  await expect(
    page.getByRole("heading", { name: /遊び方ガイド|Play Style Guide/i }),
  ).toBeVisible();
  return page.locator(".guide-screen__card").filter({
    has: page.getByRole("heading", {
      name: /現実の日時・天気とWeb検索|Real-world Date, Weather & Web Search/i,
    }),
  });
}

test("遊び方ガイドのカードはデバッグモードが無効なら表示しない", async ({
  page,
}) => {
  const card = await openGuide(page, BASE_USER_SETTINGS);
  await expect(card).toHaveCount(0);
});

test("遊び方ガイドのカードはデバッグモードが有効なときだけ表示する", async ({
  page,
}) => {
  const card = await openGuide(page, {
    ...BASE_USER_SETTINGS,
    prompt_preview_enabled: true,
  });
  await expect(card).toBeVisible();
  await expect(card.locator(".guide-screen__toggle")).toHaveCount(2);
});
