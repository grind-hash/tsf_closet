import { fileURLToPath } from "node:url";
import { expect, type Page, test } from "@playwright/test";

// リポジトリ内の実画像を参照する（絶対パス固定だと他環境で ENOENT になる）
const IMAGE_PATH = fileURLToPath(
  new URL("../../../backend/images/characters/char1_v2.png", import.meta.url),
);

const SESSION_ID = "pe-session-1";
const ENTRY_ID = "pe-entry-1";
const ENTRY_INSTRUCTION = "銀髪の少女が赤いドレスで街を歩く";
const ENTRY_FINAL_PROMPT = "1girl, silver hair, red dress";
const EXPANDED_PROMPT = "1girl, silver hair, red dress, walking, city street";
const EXPANDED_NEGATIVE = "lowres, bad anatomy, blurry";
// ギャラリー画像は API 相対パスで返る（表示側で /api を付ける）
const GALLERY_IMAGE = "/mock-scene.png";

type PromptExpanderSessionPayload = {
  id: string;
  title: string;
  entry_count: number;
  thumbnail_url: string | null;
  created_at: string;
  updated_at: string;
};

type PromptExpanderEntryPayload = {
  id: string;
  session_id: string;
  kind: "generated" | "uploaded";
  instruction: string | null;
  positive_expand_mode: "off" | "japanese" | "tags";
  negative_expand_mode: "off" | "japanese" | "tags";
  character_mode: boolean;
  final_prompt: string;
  final_negative_prompt: string;
  character_prompts: string[];
  image_model: string | null;
  text_model: string | null;
  seed: number | null;
  i2i_strength: number | null;
  i2i_noise: number | null;
  image_size: "portrait" | "landscape" | "square" | null;
  source_kind: "none" | "history" | "entry" | "upload";
  source_history_id: string | null;
  source_entry_id: string | null;
  image_url: string;
  nsfw: boolean | null;
  created_at: string;
};

function sessionPayload(
  overrides: Partial<PromptExpanderSessionPayload> = {},
): PromptExpanderSessionPayload {
  return {
    id: SESSION_ID,
    title: "テストセッション",
    entry_count: 1,
    thumbnail_url: `/prompt-expander/images/${ENTRY_ID}`,
    created_at: "2026-08-01T00:00:00",
    updated_at: "2026-08-01T00:00:00",
    ...overrides,
  };
}

function entryPayload(
  overrides: Partial<PromptExpanderEntryPayload> = {},
): PromptExpanderEntryPayload {
  return {
    id: ENTRY_ID,
    session_id: SESSION_ID,
    kind: "generated",
    instruction: ENTRY_INSTRUCTION,
    positive_expand_mode: "tags",
    negative_expand_mode: "off",
    character_mode: false,
    final_prompt: ENTRY_FINAL_PROMPT,
    final_negative_prompt: "lowres",
    character_prompts: [],
    image_model: "nai-diffusion-4-5-full",
    text_model: "glm-4-6",
    seed: 12345,
    i2i_strength: null,
    i2i_noise: null,
    image_size: "portrait",
    source_kind: "none",
    source_history_id: null,
    source_entry_id: null,
    image_url: `/prompt-expander/images/${ENTRY_ID}`,
    nsfw: false,
    created_at: "2026-08-01T00:00:00",
    ...overrides,
  };
}

function settingsPayload() {
  return {
    settings: {
      text_model: "glm-4-6",
      image_model: "nai-diffusion-4-5-full",
      image_size: "portrait",
      i2i_strength: 0.7,
      i2i_noise: 0,
      seed: null,
      memory_text: "",
      use_memory: true,
      confirm_before_generate: true,
      inherit_source_prompts: true,
    },
    text_model_options: [
      { id: "glm-4-6", label: "GLM 4.6" },
      { id: "xialong-v1", label: "Xialong v1" },
    ],
    image_model_options: [
      "nai-diffusion-5-full",
      "nai-diffusion-5-curated",
      "nai-diffusion-4-5-full",
      "nai-diffusion-4-5-curated",
    ],
    max_character_prompts: {
      "nai-diffusion-5-full": 22,
      "nai-diffusion-5-curated": 22,
      "nai-diffusion-4-5-full": 6,
      "nai-diffusion-4-5-curated": 6,
    },
    image_sizes: ["portrait", "landscape", "square"],
    novelai_configured: true,
  };
}

function runPayload() {
  return {
    id: "run-1",
    source_session_id: null,
    source_history_id: null,
    source_prompt_expander_entry_id: ENTRY_ID,
    scenario_template_id: null,
    preset: "disguise",
    title: "仮面舞踏会への潜入",
    objective: "仮面舞踏会で銀色の封蝋がある招待状の差出人を特定する",
    setting: "企業主催の仮面舞踏会",
    constraints: ["招待状を持っていない"],
    status: "active",
    turn_count: 0,
    max_turns: 8,
    remaining_turns: 8,
    ending_title: null,
    ending_summary: null,
    clues: [],
    milestones: [{ id: "gain_access", label: "侵入経路を確保" }],
    completed_milestones: [],
    opening_narrative: "変身後の姿で舞踏会の入口に立っている。",
    choices: [{ id: "a", label: "受付を観察する" }],
    current_image_url: GALLERY_IMAGE,
    current_image_prompt: null,
    use_precise_reference: false,
    enable_composite_scene: false,
    opening_image_url: GALLERY_IMAGE,
    background_image_url: GALLERY_IMAGE,
    portrait_image_url: GALLERY_IMAGE,
    opening_portrait_url: GALLERY_IMAGE,
    visual_state: null,
    turns: [],
    created_at: "2026-08-01T00:00:00",
    updated_at: "2026-08-01T00:00:00",
  };
}

type FeatureFlags = {
  experimentalPromptExpanderEnabled?: boolean;
  experimentalAdventureEnabled?: boolean;
};

async function enableFeatures(page: Page, flags: FeatureFlags) {
  await page.addInitScript((settings) => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
    window.localStorage.setItem("novelai_opus_confirmed", "true");
    window.localStorage.setItem("app_settings", JSON.stringify(settings));
  }, flags);
}

/** Prompt Expander と、その画面が起動時に叩く共通 API のモック */
async function mockPromptExpanderApis(page: Page) {
  const state = {
    sessions: [sessionPayload()] as PromptExpanderSessionPayload[],
    entries: [entryPayload()] as PromptExpanderEntryPayload[],
    expandBodies: [] as Record<string, unknown>[],
    generateBodies: [] as Record<string, unknown>[],
  };
  let generatedCount = 0;

  await page.route("**/api/game/anlas", async (route) => {
    await route.fulfill({
      json: { total_anlas: 100, fixed_anlas: 100, purchased_anlas: 0 },
    });
  });
  await page.route("**/api/memory/text", async (route) => {
    await route.fulfill({ json: { memory_text: "" } });
  });
  await page.route(
    (url) => url.pathname.startsWith("/api/prompt-expander/images/"),
    async (route) => {
      await route.fulfill({ path: IMAGE_PATH, contentType: "image/png" });
    },
  );
  await page.route(
    (url) => url.pathname === "/api/prompt-expander/settings",
    async (route) => {
      // GET / PUT とも同じ設定を返す（PUT は送信内容を上書き反映する）
      const payload = settingsPayload();
      if (route.request().method() === "PUT") {
        const patch = route.request().postDataJSON() as Record<string, unknown>;
        payload.settings = { ...payload.settings, ...patch };
      }
      await route.fulfill({ json: payload });
    },
  );
  await page.route(
    (url) => url.pathname === "/api/prompt-expander/sessions",
    async (route) => {
      if (route.request().method() === "POST") {
        const body = (route.request().postDataJSON() ?? {}) as {
          title?: string;
        };
        const created = sessionPayload({
          id: "pe-session-2",
          title: body.title ?? "",
          entry_count: 0,
          thumbnail_url: null,
        });
        state.sessions.unshift(created);
        await route.fulfill({ status: 201, json: created });
        return;
      }
      await route.fulfill({ json: { sessions: state.sessions } });
    },
  );
  await page.route(
    (url) => /^\/api\/prompt-expander\/sessions\/[^/]+$/.test(url.pathname),
    async (route) => {
      const id = new URL(route.request().url()).pathname.split("/").pop();
      const session = state.sessions.find((item) => item.id === id);
      if (!session) {
        await route.fulfill({ status: 404, json: { detail: "not found" } });
        return;
      }
      await route.fulfill({
        json: {
          session,
          entries: id === SESSION_ID ? state.entries : [],
        },
      });
    },
  );
  await page.route(
    (url) =>
      /^\/api\/prompt-expander\/sessions\/[^/]+\/generate$/.test(url.pathname),
    async (route) => {
      const body = route.request().postDataJSON() as {
        prompt: string;
        negative_prompt?: string;
        character_prompts?: string[];
        instruction?: string | null;
        positive_expand_mode: "off" | "japanese" | "tags";
        negative_expand_mode: "off" | "japanese" | "tags";
      };
      state.generateBodies.push(body);
      generatedCount += 1;
      const entry = entryPayload({
        id: `pe-entry-new-${generatedCount}`,
        instruction: body.instruction ?? null,
        final_prompt: body.prompt,
        final_negative_prompt: body.negative_prompt ?? "",
        character_prompts: body.character_prompts ?? [],
        positive_expand_mode: body.positive_expand_mode,
        negative_expand_mode: body.negative_expand_mode,
        image_url: `/prompt-expander/images/pe-entry-new-${generatedCount}`,
        created_at: "2026-08-02T00:00:00",
      });
      state.entries.unshift(entry);
      await route.fulfill({ json: { entry, anlas: null } });
    },
  );
  await page.route(
    (url) => url.pathname === "/api/prompt-expander/expand",
    async (route) => {
      const body = route.request().postDataJSON() as {
        expand_positive?: boolean;
        expand_negative?: boolean;
      };
      state.expandBodies.push(body as Record<string, unknown>);
      await route.fulfill({
        json: {
          positive_prompt:
            body.expand_positive === false ? null : EXPANDED_PROMPT,
          character_prompts: null,
          negative_prompt: body.expand_negative ? EXPANDED_NEGATIVE : null,
          text_model: "glm-4-6",
        },
      });
    },
  );
  await page.route(
    (url) => url.pathname === "/api/prompt-expander/entries",
    async (route) => {
      await route.fulfill({
        json: {
          items: state.entries,
          total: state.entries.length,
          page: 1,
          page_size: 24,
          has_more: false,
        },
      });
    },
  );
  await page.route(
    (url) => /^\/api\/prompt-expander\/entries\/[^/]+$/.test(url.pathname),
    async (route) => {
      const id = new URL(route.request().url()).pathname.split("/").pop();
      const entry = state.entries.find((item) => item.id === id);
      if (!entry) {
        await route.fulfill({ status: 404, json: { detail: "not found" } });
        return;
      }
      await route.fulfill({ json: entry });
    },
  );
  return state;
}

/** 通常プレイ(WelcomeScreen)が起動時に叩く API のモック */
async function mockGameApis(page: Page) {
  await page.route("**/api/game/characters", async (route) => {
    await route.fulfill({ json: { characters: [] } });
  });
  await page.route("**/api/game/custom-characters", async (route) => {
    await route.fulfill({ json: { characters: [] } });
  });
}

/** TSFシナリオのセットアップ画面が必要とする API の最小モック */
async function mockAdventureApis(page: Page) {
  const state = {
    setupBodies: [] as Record<string, unknown>[],
    createBodies: [] as Record<string, unknown>[],
  };
  await page.route("**/api/mock-scene.png", async (route) => {
    await route.fulfill({ path: IMAGE_PATH, contentType: "image/png" });
  });
  await page.route("**/api/gallery/sessions?*", async (route) => {
    await route.fulfill({
      json: {
        sessions: [
          {
            session_id: "session-1",
            character_name: "テストキャラクター",
            thumbnail_url: GALLERY_IMAGE,
            item_count: 1,
            first_timestamp: "2026-08-01T00:00:00",
            last_timestamp: "2026-08-01T00:00:00",
            last_instruction: "赤いドレスを着て街を歩く",
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        has_more: false,
      },
    });
  });
  await page.route("**/api/gallery?*", async (route) => {
    await route.fulfill({
      json: { items: [], total: 0, page: 1, page_size: 50, has_more: false },
    });
  });
  await page.route("**/api/adventure/templates", async (route) => {
    await route.fulfill({ json: { templates: [] } });
  });
  await page.route("**/api/adventure/setup/generate", async (route) => {
    state.setupBodies.push(
      route.request().postDataJSON() as Record<string, unknown>,
    );
    await route.fulfill({
      json: {
        setting: "企業主催の仮面舞踏会",
        objective: "仮面舞踏会で銀色の封蝋がある招待状の差出人を特定する",
        constraints: ["招待状を持っていない"],
      },
    });
  });
  await page.route("**/api/adventure/runs", async (route) => {
    if (route.request().method() === "POST") {
      state.createBodies.push(
        route.request().postDataJSON() as Record<string, unknown>,
      );
      await route.fulfill({ status: 201, json: runPayload() });
      return;
    }
    await route.fulfill({ json: { runs: [] } });
  });
  await page.route("**/api/adventure/runs/run-1", async (route) => {
    await route.fulfill({ json: runPayload() });
  });
  return state;
}

/** コンポーザの欄（ラベル文言は拡張由来バッジが付くことがあるので id で特定する） */
function positiveField(page: Page) {
  return page.locator("#prompt-expander-positive");
}

function negativeField(page: Page) {
  return page.locator("#prompt-expander-negative");
}

function positiveToolbar(page: Page) {
  return page.getByRole("toolbar", { name: "プロンプト欄の操作" });
}

function negativeToolbar(page: Page) {
  return page.getByRole("toolbar", { name: "ネガティブ欄の操作" });
}

function generateButton(page: Page) {
  return page.getByRole("button", { name: "生成", exact: true });
}

async function openSession(page: Page) {
  await page.goto(`/prompt-expander/${SESSION_ID}`);
  await expect(positiveField(page)).toBeVisible();
}

test("side menu shows Prompt Expander only when the flag is on", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  await mockGameApis(page);
  await page.goto("/play/new");

  const menu = page.getByRole("navigation", { name: "メインメニュー" });
  await menu.getByRole("button", { name: "Prompt Expander" }).click();
  await expect(page).toHaveURL(/\/prompt-expander$/);
  await expect(
    page.getByRole("heading", { level: 1, name: /Prompt Expander/ }),
  ).toBeVisible();
  await expect(page.getByText("テストセッション")).toBeVisible();
});

test("prompt expander route redirects and menu hides when disabled", async ({
  page,
}) => {
  await enableFeatures(page, {});
  await mockGameApis(page);
  await page.goto("/prompt-expander");
  await expect(page).toHaveURL(/\/play\/new$/);
  const menu = page.getByRole("navigation", { name: "メインメニュー" });
  await expect(menu.getByRole("button", { name: "新規プレイ" })).toBeVisible();
  await expect(
    menu.getByRole("button", { name: "Prompt Expander" }),
  ).toHaveCount(0);
});

test("creating a session opens the composer", async ({ page }) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  await page.goto("/prompt-expander");

  await page
    .getByLabel("新しいセッションのタイトル（省略可）")
    .fill("新しいテスト");
  await page.getByRole("button", { name: "新規セッション" }).click();
  await expect(page).toHaveURL(/\/prompt-expander\/pe-session-2$/);
  await expect(positiveField(page)).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 2, name: "新しいテスト" }),
  ).toBeVisible();
});

test("expand with tags from the field toolbar, edit the inline result and generate", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  // 正プロンプト欄の右上ツールバー: モード（既定はタグ）+ 拡張 + 提案
  const toolbar = positiveToolbar(page);
  await expect(
    toolbar.getByRole("radio", { name: "タグで拡張" }),
  ).toBeChecked();
  await expect(toolbar.getByRole("button", { name: "✨ 提案" })).toBeEnabled();
  // 空欄のうちは拡張できない（理由付き）
  const expandButton = toolbar.getByRole("button", { name: "拡張" });
  await expect(expandButton).toBeDisabled();
  await expect(expandButton).toHaveAttribute(
    "title",
    "拡張する内容を入力してください",
  );

  const instruction = "猫耳メイドがカフェで微笑む";
  await positiveField(page).fill(instruction);
  await expandButton.click();

  await expect.poll(() => state.expandBodies.length).toBe(1);
  expect(state.expandBodies[0]).toMatchObject({
    instruction,
    expand_positive: true,
    positive_mode: "tags",
    character_mode: false,
    expand_negative: false,
    inherit_source_prompts: true,
  });
  expect(state.expandBodies[0]).not.toHaveProperty("current_prompt");

  // 拡張結果は欄の直下にインライン表示され、編集できる
  const card = page.getByRole("region", { name: "拡張結果（プロンプト）" });
  await expect(card).toBeVisible();
  const basePrompt = card.getByLabel("ベースプロンプト");
  await expect(basePrompt).toHaveValue(EXPANDED_PROMPT);
  // カードが開いている間は下の「生成」は押せない（理由付き）
  await expect(generateButton(page)).toBeDisabled();
  const edited = `${EXPANDED_PROMPT}, smile`;
  await basePrompt.fill(edited);
  expect(state.generateBodies).toHaveLength(0);
  await card.getByRole("button", { name: "この内容で生成" }).click();

  await expect.poll(() => state.generateBodies.length).toBe(1);
  expect(state.generateBodies[0]).toMatchObject({
    prompt: edited,
    instruction,
    positive_expand_mode: "tags",
    negative_expand_mode: "off",
    image_model: "nai-diffusion-4-5-full",
  });
  await expect(card).toBeHidden();
  // 「この内容で生成」は欄を書き換えない（指示のまま残る）
  await expect(positiveField(page)).toHaveValue(instruction);

  // 生成したエントリが一覧の先頭に並ぶ
  const entries = page.locator(".prompt-expander__entry-list > li");
  await expect(entries).toHaveCount(2);
  await expect(entries.nth(0)).toContainText(instruction);
  await expect(entries.nth(1)).toContainText(ENTRY_INSTRUCTION);
});

test("apply the expansion to the field and generate with the expand metadata", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  const instruction = "雨の日の駅で傘を差す少女";
  await positiveField(page).fill(instruction);
  await positiveToolbar(page).getByRole("button", { name: "拡張" }).click();
  const card = page.getByRole("region", { name: "拡張結果（プロンプト）" });
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "欄へ反映" }).click();

  await expect(card).toBeHidden();
  await expect(positiveField(page)).toHaveValue(EXPANDED_PROMPT);
  // 拡張由来であることがラベル横のバッジで分かる
  await expect(
    page.locator('label[for="prompt-expander-positive"]'),
  ).toContainText("タグ拡張");
  expect(state.generateBodies).toHaveLength(0);

  await generateButton(page).click();
  await expect.poll(() => state.generateBodies.length).toBe(1);
  expect(state.generateBodies[0]).toMatchObject({
    prompt: EXPANDED_PROMPT,
    instruction,
    positive_expand_mode: "tags",
    negative_expand_mode: "off",
  });
});

test("negative field has its own expand toolbar and inline result", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  await positiveField(page).fill("1girl, raw prompt");
  await negativeField(page).fill("低品質なもの");
  const toolbar = negativeToolbar(page);
  // ラジオ本体は見た目上隠れているので、ラベル（チップ）をクリックして切り替える
  await toolbar
    .locator(".prompt-expander__radio", { hasText: "日本語で拡張" })
    .click();
  await expect(
    toolbar.getByRole("radio", { name: "日本語で拡張" }),
  ).toBeChecked();
  await toolbar.getByRole("button", { name: "拡張" }).click();

  await expect.poll(() => state.expandBodies.length).toBe(1);
  expect(state.expandBodies[0]).toMatchObject({
    expand_positive: false,
    expand_negative: true,
    negative_mode: "japanese",
    negative_instruction: "低品質なもの",
  });

  const card = page.getByRole("region", { name: "拡張結果（ネガティブ）" });
  await expect(card).toBeVisible();
  await expect(card.getByLabel("ネガティブプロンプト")).toHaveValue(
    EXPANDED_NEGATIVE,
  );
  await card.getByRole("button", { name: "欄へ反映" }).click();
  await expect(card).toBeHidden();
  await expect(negativeField(page)).toHaveValue(EXPANDED_NEGATIVE);

  await generateButton(page).click();
  await expect.poll(() => state.generateBodies.length).toBe(1);
  expect(state.generateBodies[0]).toMatchObject({
    prompt: "1girl, raw prompt",
    negative_prompt: EXPANDED_NEGATIVE,
    instruction: null,
    positive_expand_mode: "off",
    negative_expand_mode: "japanese",
  });
});

test("generate without expansion sends the raw prompt", async ({ page }) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  await expect(generateButton(page)).toBeDisabled();
  await positiveField(page).fill("1girl, raw prompt");
  await generateButton(page).click();

  await expect.poll(() => state.generateBodies.length).toBe(1);
  expect(state.expandBodies).toHaveLength(0);
  expect(state.generateBodies[0]).toMatchObject({
    prompt: "1girl, raw prompt",
    instruction: null,
    positive_expand_mode: "off",
    negative_expand_mode: "off",
  });
  await expect(
    page.locator(".prompt-expander__entry-list > li").first(),
  ).toContainText("1girl, raw prompt");
});

test("composer sections collapse, expand and persist to localStorage", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  await openSession(page);

  // 並び順: 生成パラメータ → プロンプト／指示 → キャラクタープロンプト → i2i設定
  const headings = page.locator(
    ".prompt-expander__composer .prompt-expander__section-toggle",
  );
  await expect(headings).toHaveText([
    /生成パラメータ/,
    /プロンプト／指示/,
    /キャラクタープロンプト/,
    /i2i設定/,
  ]);

  const paramsToggle = page.getByRole("button", { name: "生成パラメータ" });
  const imageModel = page.getByLabel("画像モデル");
  await expect(paramsToggle).toHaveAttribute("aria-expanded", "true");
  await expect(imageModel).toBeVisible();
  await paramsToggle.click();
  await expect(paramsToggle).toHaveAttribute("aria-expanded", "false");
  await expect(imageModel).toBeHidden();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          JSON.parse(
            localStorage.getItem("prompt_expander_sections_open") ?? "{}",
          ).params,
      ),
    )
    .toBe(false);

  // 見出し右のツールバー操作はセクションを開閉しない
  const charToggle = page.getByRole("button", {
    name: "キャラクタープロンプト",
  });
  await expect(charToggle).toHaveAttribute("aria-expanded", "true");
  await page
    .locator(".prompt-expander__switch", { hasText: "キャラクタープロンプト" })
    .click();
  await expect(
    page.getByRole("checkbox", { name: "キャラクタープロンプト" }),
  ).toBeChecked();
  await expect(charToggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("button", { name: "＋ 追加" })).toBeVisible();

  // 再読み込み後も折りたたみ状態が残る
  await page.reload();
  await expect(positiveField(page)).toBeVisible();
  await expect(paramsToggle).toHaveAttribute("aria-expanded", "false");
  await expect(imageModel).toBeHidden();
  await paramsToggle.click();
  await expect(imageModel).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          JSON.parse(
            localStorage.getItem("prompt_expander_sections_open") ?? "{}",
          ).params,
      ),
    )
    .toBe(true);
});

test("settings open as a right side panel and remember the state", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  await openSession(page);

  const panel = page.getByRole("region", { name: "Prompt Expander 設定" });
  const headerButton = page
    .locator(".prompt-expander__header")
    .getByRole("button", { name: "設定", exact: true });
  await expect(panel).toBeHidden();
  await expect(headerButton).toHaveAttribute("aria-expanded", "false");

  await headerButton.click();
  await expect(panel).toBeVisible();
  await expect(headerButton).toHaveAttribute("aria-expanded", "true");
  await expect(
    panel.getByLabel("テキストモデル（拡張・提案に使用）"),
  ).toBeVisible();
  await expect(panel.getByLabel("Prompt Expander メモリ")).toBeVisible();
  // 「拡張結果を確認してから生成」は廃止、参照元の引き継ぎは i2i 設定側へ移動
  await expect(panel.getByText("拡張結果を確認してから生成")).toHaveCount(0);
  await expect(panel.getByText("参照元のプロンプトを引き継ぐ")).toHaveCount(0);
  await expect(
    page.getByRole("checkbox", { name: "参照元のプロンプトを引き継ぐ" }),
  ).toBeChecked();
  await expect
    .poll(() =>
      page.evaluate(() =>
        localStorage.getItem("prompt_expander_settings_panel_open"),
      ),
    )
    .toBe("true");

  await page.reload();
  await expect(positiveField(page)).toBeVisible();
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: "設定を閉じる" }).click();
  await expect(panel).toBeHidden();
  await expect
    .poll(() =>
      page.evaluate(() =>
        localStorage.getItem("prompt_expander_settings_panel_open"),
      ),
    )
    .toBe("false");
});

test("restore fills the composer from an entry", async ({ page }) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  await openSession(page);

  const textarea = positiveField(page);
  await expect(textarea).toHaveValue("");
  await page
    .locator(".prompt-expander__entry-list > li")
    .first()
    .getByRole("button", { name: "欄へ復元" })
    .click();
  await expect(textarea).toHaveValue(ENTRY_FINAL_PROMPT);
  await expect(negativeField(page)).toHaveValue("lowres");
});

test("use in normal play preloads the welcome screen", async ({ page }) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  await mockGameApis(page);
  await openSession(page);

  await page
    .locator(".prompt-expander__entry-list > li")
    .first()
    .getByRole("button", { name: "通常プレイで使う" })
    .click();

  // ?pe_entry= は取り込み後に消える
  await expect(page).toHaveURL(/\/play\/new$/);
  const welcome = page.locator(".welcome-screen");
  await expect(welcome).toBeVisible();
  const preview = welcome.locator(".welcome-screen__custom-preview img");
  await expect(preview).toBeVisible();
  await expect(preview).toHaveAttribute("src", /^data:image\/png;base64,/);
  // タグ拡張のエントリは最終プロンプトを外見タグ欄に前埋めする
  await expect(welcome.getByPlaceholder(/外見タグ/)).toHaveValue(
    ENTRY_FINAL_PROMPT,
  );
  await expect(
    welcome.getByRole("button", { name: "ゲームを開始" }),
  ).toBeEnabled();
});

test("welcome screen picks an entry from the Prompt Expander modal", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  await mockGameApis(page);
  await page.goto("/play/new");

  const welcome = page.locator(".welcome-screen");
  await welcome
    .getByRole("button", { name: "Prompt Expander から選択" })
    .click();
  const dialog = page.getByRole("dialog", { name: "Prompt Expander から選択" });
  await dialog.getByRole("button", { name: ENTRY_INSTRUCTION }).click();
  await expect(dialog).toBeHidden();
  await expect(
    welcome.locator(".welcome-screen__custom-preview img"),
  ).toBeVisible();
  await expect(welcome.getByPlaceholder(/外見タグ/)).toHaveValue(
    ENTRY_FINAL_PROMPT,
  );
});

test("welcome screen hides the Prompt Expander button when disabled", async ({
  page,
}) => {
  await enableFeatures(page, {});
  await mockGameApis(page);
  await page.goto("/play/new");
  const welcome = page.locator(".welcome-screen");
  await expect(
    welcome.getByRole("button", { name: "📁 画像を選択" }),
  ).toBeVisible();
  await expect(
    welcome.getByRole("button", { name: "Prompt Expander から選択" }),
  ).toHaveCount(0);
});

test("adventure setup can start from a Prompt Expander entry", async ({
  page,
}) => {
  await enableFeatures(page, {
    experimentalPromptExpanderEnabled: true,
    experimentalAdventureEnabled: true,
  });
  await mockPromptExpanderApis(page);
  await mockGameApis(page);
  const state = await mockAdventureApis(page);
  await page.goto("/adventure");

  const sourceCard = page.locator(".adventure-card--source");
  await expect(sourceCard.getByRole("group")).toContainText(
    "テストキャラクター",
  );
  await sourceCard.getByRole("button", { name: "変更" }).click();
  const picker = page.getByRole("dialog", { name: "開始セッション" });
  const tabs = picker.getByRole("tab");
  await expect(tabs).toHaveCount(3);
  await picker.getByRole("tab", { name: "Prompt Expander" }).click();
  await picker.getByRole("button", { name: ENTRY_INSTRUCTION }).click();
  await expect(picker).toBeHidden();
  await expect(sourceCard.getByRole("group")).toContainText("Prompt Expander");
  await expect(sourceCard.getByRole("group")).toContainText(ENTRY_INSTRUCTION);

  await page.getByRole("button", { name: /^なりすまし・着替え/ }).click();
  await page.getByRole("button", { name: "ミッション案を自動生成" }).click();
  await expect.poll(() => state.setupBodies.length).toBe(1);
  expect(state.setupBodies[0]).toMatchObject({
    source_prompt_expander_entry_id: ENTRY_ID,
    preset: "disguise",
  });
  expect(state.setupBodies[0]).not.toHaveProperty("source_session_id");
  await expect(page.getByLabel("舞台")).toHaveValue("企業主催の仮面舞踏会");

  await page.getByRole("button", { name: "シナリオを開始" }).click();
  await expect(page).toHaveURL(/\/adventure\/run-1$/);
  expect(state.createBodies[0]).toMatchObject({
    source_prompt_expander_entry_id: ENTRY_ID,
  });
  expect(state.createBodies[0]).not.toHaveProperty("source_session_id");
});

test("adventure deep link preselects the Prompt Expander entry", async ({
  page,
}) => {
  await enableFeatures(page, {
    experimentalPromptExpanderEnabled: true,
    experimentalAdventureEnabled: true,
  });
  await mockPromptExpanderApis(page);
  await mockGameApis(page);
  await mockAdventureApis(page);
  await page.goto(`/adventure?pe_entry=${ENTRY_ID}`);

  await expect(page).toHaveURL(/\/adventure$/);
  const sourceCard = page.locator(".adventure-card--source");
  await expect(sourceCard.getByRole("group")).toContainText("Prompt Expander");
  await expect(sourceCard.getByRole("group")).toContainText(ENTRY_INSTRUCTION);
  await expect(
    page.getByRole("button", { name: "ミッション案を自動生成" }),
  ).toBeEnabled();
});

test("romance player picker does not offer the Prompt Expander tab", async ({
  page,
}) => {
  await enableFeatures(page, {
    experimentalPromptExpanderEnabled: true,
    experimentalAdventureEnabled: true,
  });
  await mockPromptExpanderApis(page);
  await mockGameApis(page);
  await mockAdventureApis(page);
  await page.goto("/adventure");

  await page.getByRole("button", { name: /^恋愛シミュレーション/ }).click();
  await page.getByLabel(/主人公（自分）/).selectOption("__session__");
  const playerSource = page.locator(".adventure-romance-player-source");
  await expect(playerSource.getByRole("group")).toContainText(
    "テストキャラクター",
  );
  await playerSource.getByRole("button", { name: "変更" }).click();
  const picker = page.getByRole("dialog", { name: "主人公にするセッション" });
  await expect(picker.getByRole("tab")).toHaveCount(2);
  await expect(
    picker.getByRole("tab", { name: "Prompt Expander" }),
  ).toHaveCount(0);
});
