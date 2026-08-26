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
// 64x64: ほぼ白 (252,251,250) の背景に赤い 20x20 の正方形。背景切り抜きの対象になる
// （adventure-portrait-alpha.spec.ts と同じ画像）
const WHITE_BG_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAAmUlEQVR4nO3ZsQ3CQBQE0bkR7ZBRAYW7Amd0gx3Qgy84jczL92ulDf84jy9lEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEidxEveYP7E/35ezr8929wUkTuIkTuIkTuIkTuIkTuIkTuIkTuIkTuIkTuLG/1O/mMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMRJnMS5usCsH/HgCWNvKE7YAAAAAElFTkSuQmCC";

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
  manga_mode: boolean;
  manga_panel_count: number | null;
  source_kind: "none" | "history" | "entry" | "upload";
  source_history_id: string | null;
  source_entry_id: string | null;
  transparent_background: boolean;
  reference_kind: "none" | "history" | "entry" | "upload";
  reference_history_id: string | null;
  reference_entry_id: string | null;
  reference_type: "character" | "style" | "character&style" | null;
  reference_strength: number | null;
  reference_fidelity: number | null;
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
    manga_mode: false,
    manga_panel_count: null,
    source_kind: "none",
    source_history_id: null,
    source_entry_id: null,
    transparent_background: false,
    reference_kind: "none",
    reference_history_id: null,
    reference_entry_id: null,
    reference_type: null,
    reference_strength: null,
    reference_fidelity: null,
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
      restore_seed: false,
      memory_text: "",
      use_memory: true,
      confirm_before_generate: true,
      inherit_source_prompts: true,
      manga_mode: false,
      manga_panel_count: 0,
      manga_layout: "auto",
      manga_dialogue: true,
      manga_text_language: "auto",
      manga_sound_effects: true,
      manga_reading_direction: "rtl",
      manga_narration: false,
      use_precise_reference: false,
      reference_type: "character",
      reference_strength: 0.85,
      reference_fidelity: 1,
      transparent_background: false,
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
    reference_types: ["character", "style", "character&style"],
    anlas_per_reference: 5,
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
    suggestBodies: [] as Record<string, unknown>[],
    scriptBodies: [] as Record<string, unknown>[],
    // 設定 PUT の送信内容（部分更新）を順に記録する
    settingsBodies: [] as Record<string, unknown>[],
    // PUT の部分更新を積み上げて保持する（複数回の設定変更をまたいで検証するため）
    settings: settingsPayload().settings as Record<string, unknown>,
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
      // GET / PUT とも同じ設定を返す（PUT は送信内容を上書き反映して保持する）
      const payload = settingsPayload();
      if (route.request().method() === "PUT") {
        const patch = route.request().postDataJSON() as Record<string, unknown>;
        state.settingsBodies.push(patch);
        state.settings = { ...state.settings, ...patch };
      }
      await route.fulfill({
        json: { ...payload, settings: state.settings },
      });
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
        image_model?: string;
        manga_mode?: boolean;
        manga_panel_count?: number | null;
        transparent_background?: boolean;
        reference_kind?: "none" | "history" | "entry" | "upload";
        reference_history_id?: string;
        reference_entry_id?: string;
        reference_type?: "character" | "style" | "character&style";
        reference_strength?: number;
        reference_fidelity?: number;
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
        image_model: body.image_model ?? "nai-diffusion-4-5-full",
        manga_mode: body.manga_mode ?? false,
        manga_panel_count: body.manga_mode
          ? (body.manga_panel_count ?? null)
          : null,
        transparent_background: body.transparent_background ?? false,
        reference_kind: body.reference_kind ?? "none",
        reference_history_id: body.reference_history_id ?? null,
        reference_entry_id: body.reference_entry_id ?? null,
        reference_type: body.reference_kind
          ? (body.reference_type ?? null)
          : null,
        reference_strength: body.reference_kind
          ? (body.reference_strength ?? null)
          : null,
        reference_fidelity: body.reference_kind
          ? (body.reference_fidelity ?? null)
          : null,
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
    (url) => url.pathname === "/api/prompt-expander/manga-script",
    async (route) => {
      const body = route.request().postDataJSON() as { instruction: string };
      state.scriptBodies.push(body);
      await route.fulfill({
        json: {
          script: `①${body.instruction}。彼女が鏡を見る「え…？」\n②体が変わっていく《ドクン》`,
          text_model: "glm-4-6",
        },
      });
    },
  );
  await page.route(
    (url) => url.pathname === "/api/prompt-expander/suggest-characters",
    async (route) => {
      state.suggestBodies.push(
        route.request().postDataJSON() as Record<string, unknown>,
      );
      await route.fulfill({
        json: {
          suggestions: [
            { title: "銀髪の少女", prompt: "1girl, silver hair, blue eyes" },
            { title: "金髪の少女", prompt: "1girl, blonde hair, green eyes" },
          ],
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
  await expect(toolbar.getByRole("radio", { name: "タグ" })).toBeChecked();
  await expect(toolbar.getByRole("button", { name: "✨ 提案" })).toBeEnabled();
  // 空欄のうちは拡張できない（理由付き）
  const expandButton = toolbar.getByRole("button", {
    name: "LLMでプロンプト化",
  });
  await expect(expandButton).toBeDisabled();
  await expect(expandButton).toHaveAttribute(
    "title",
    "プロンプト化する内容を入力してください",
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
  const card = page.getByRole("region", { name: "変換結果（プロンプト）" });
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
  // 確認カードは生成後も残る（同じ内容で繰り返す・微調整して再生成できる）
  await expect(card).toBeVisible();
  await expect(basePrompt).toHaveValue(edited);
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
  await positiveToolbar(page)
    .getByRole("button", { name: "LLMでプロンプト化" })
    .click();
  const card = page.getByRole("region", { name: "変換結果（プロンプト）" });
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "欄へ反映" }).click();

  await expect(card).toBeHidden();
  await expect(positiveField(page)).toHaveValue(EXPANDED_PROMPT);
  // 拡張由来であることがラベル横のバッジで分かる
  await expect(
    page.locator('label[for="prompt-expander-positive"]'),
  ).toContainText("タグで変換");
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
    .locator(".prompt-expander__radio", { hasText: "日本語文" })
    .click();
  await expect(toolbar.getByRole("radio", { name: "日本語文" })).toBeChecked();
  await toolbar.getByRole("button", { name: "LLMでプロンプト化" }).click();

  await expect.poll(() => state.expandBodies.length).toBe(1);
  expect(state.expandBodies[0]).toMatchObject({
    expand_positive: false,
    expand_negative: true,
    negative_mode: "japanese",
    negative_instruction: "低品質なもの",
  });

  const card = page.getByRole("region", { name: "変換結果（ネガティブ）" });
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

test("comic mode is V5-only, its options are sent with expand/generate, and entries get a badge", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  // 既定は閉じているが、見出し右のトグルと要約は見える。V4.5 では無効で理由が分かる
  const mangaHeading = page.getByRole("button", { name: "漫画（コマ割り）" });
  await expect(mangaHeading).toHaveAttribute("aria-expanded", "false");
  const mangaSwitch = page.getByRole("checkbox", { name: "漫画モード" });
  await expect(mangaSwitch).toBeDisabled();
  await expect(
    page.locator(".prompt-expander__section[data-section-id='manga']"),
  ).toContainText("V5 専用（現在のモデルでは無効）");
  await mangaHeading.click();
  await expect(mangaHeading).toHaveAttribute("aria-expanded", "true");
  await expect(
    page.getByText(
      /漫画モード（コマ割り・吹き出しの文字描画）は NAI Diffusion V5 系モデル専用です/,
    ),
  ).toBeVisible();

  // V5 に切り替えると有効になる
  await page.getByLabel("画像モデル").selectOption("nai-diffusion-5-full");
  await expect(mangaSwitch).toBeEnabled();
  await page
    .locator(".prompt-expander__switch", { hasText: "漫画モード" })
    .click();
  await expect(mangaSwitch).toBeChecked();
  await page.getByLabel("コマ数").selectOption("3");
  await page.getByLabel("コマ割り").selectOption("vertical");
  await page.getByLabel("セリフの言語").selectOption("ja");
  await expect(
    page.locator(".prompt-expander__section[data-section-id='manga']"),
  ).toContainText("3コマ · 縦積み · 右→左 · 日本語");
  // 読み順は日本式（右上始まり）が既定
  await expect(page.getByLabel("読み順")).toHaveValue("rtl");
  // 指示欄のプレースホルダーが漫画向けに変わり、拡張モードはタグ固定（理由つき）
  await expect(positiveField(page)).toHaveAttribute(
    "placeholder",
    /漫画にしたい流れを入力/,
  );
  const toolbar = positiveToolbar(page);
  await expect(toolbar.getByRole("radio", { name: "タグ" })).toBeChecked();
  await expect(toolbar.getByRole("radio", { name: "日本語文" })).toBeDisabled();
  await expect(
    page.getByText(/漫画モード中はコマ説明・外見を英語で組み立てます/),
  ).toBeVisible();

  // 拡張に漫画オプションが載る
  await positiveField(page).fill("男が女の子になる3コマ");
  await positiveToolbar(page)
    .getByRole("button", { name: "LLMでプロンプト化" })
    .click();
  await expect.poll(() => state.expandBodies.length).toBe(1);
  expect(state.expandBodies[0]).toMatchObject({
    manga_mode: true,
    positive_mode: "tags",
    manga: {
      panel_count: 3,
      layout: "vertical",
      dialogue: true,
      text_language: "ja",
      sound_effects: true,
      reading_direction: "rtl",
    },
  });

  // 生成にも印が載り、エントリにバッジが出る
  const card = page.getByRole("region", { name: "変換結果（プロンプト）" });
  await card.getByRole("button", { name: "この内容で生成" }).click();
  await expect.poll(() => state.generateBodies.length).toBe(1);
  expect(state.generateBodies[0]).toMatchObject({
    manga_mode: true,
    manga_panel_count: 3,
  });
  const newest = page.locator(".prompt-expander__entry-list > li").first();
  await expect(newest.locator(".prompt-expander__badge").last()).toHaveText(
    "漫画 3コマ",
  );

  // V4.5 に戻すと設定は残るが、拡張には載らない
  await page.getByLabel("画像モデル").selectOption("nai-diffusion-4-5-full");
  await expect(mangaSwitch).toBeDisabled();
  await expect(mangaSwitch).toBeChecked();
  await positiveToolbar(page)
    .getByRole("button", { name: "LLMでプロンプト化" })
    .click();
  await expect.poll(() => state.expandBodies.length).toBe(2);
  expect(state.expandBodies[1]).toMatchObject({ manga_mode: false });
  expect(state.expandBodies[1]).not.toHaveProperty("manga");
});

test("precise reference is V4.5-only, needs an image and an Anlas confirm, and is sent with generate", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  const heading = page.getByRole("button", { name: "精密参照（V4.5 系のみ）" });
  await expect(heading).toHaveAttribute("aria-expanded", "false");
  const section = page.locator(
    ".prompt-expander__section[data-section-id='reference']",
  );
  const toggle = page.getByRole("checkbox", { name: "精密参照を使う" });
  // 既定の V4.5 では使える
  await expect(toggle).toBeEnabled();
  await expect(section).toContainText("OFF");
  await heading.click();
  await expect(heading).toHaveAttribute("aria-expanded", "true");
  await expect(section).toContainText("参照 1 枚あたり +5 Anlas");

  // V5 では無効になり理由が出る（設定は保持される）
  await page.getByLabel("画像モデル").selectOption("nai-diffusion-5-full");
  await expect(toggle).toBeDisabled();
  await expect(section).toContainText("V4.5 専用（現在のモデルでは無効）");
  await expect(
    page.getByText(
      /精密参照画像（NovelAI character reference）は NAI Diffusion V4\.5 系モデル専用です/,
    ),
  ).toBeVisible();
  await page.getByLabel("画像モデル").selectOption("nai-diffusion-4-5-full");
  await expect(toggle).toBeEnabled();

  // トグル ON にしても参照画像が無ければ有効にならない
  await section
    .locator(".prompt-expander__switch", { hasText: "精密参照を使う" })
    .click();
  await expect(toggle).toBeChecked();
  await expect(section).toContainText("参照画像を選ぶと有効になります");
  await expect(page.getByLabel(/参照強度/)).toBeDisabled();

  // 画像一覧から参照画像を選ぶ（i2i 元は空のまま）
  await section.getByRole("button", { name: "履歴から選ぶ" }).click();
  const picker = page.getByRole("dialog", { name: "参照画像を選ぶ" });
  await expect(picker).toBeVisible();
  await picker.locator(".prompt-expander__entry-grid-item").first().click();
  await expect(picker).toBeHidden();
  await expect(section).toContainText(
    "キャラクター · 強度 0.85 · 忠実度 1.00 · +5 Anlas",
  );
  await expect(page.getByLabel(/参照強度/)).toBeEnabled();
  await expect(
    page.locator(".prompt-expander__section[data-section-id='i2i']"),
  ).toContainText("生成元なし");

  // 生成ボタン脇に追加 Anlas が出て、生成前に確認ダイアログを挟む
  await positiveField(page).fill("1girl, standing");
  await expect(page.locator(".prompt-expander__generate-cost")).toHaveText(
    "+5 Anlas",
  );
  await generateButton(page).click();
  await expect(
    page.getByRole("heading", { name: "Anlas 追加消費の確認" }),
  ).toBeVisible();
  await expect(page.getByText(/精密参照画像の使用により/)).toBeVisible();
  expect(state.generateBodies).toHaveLength(0);
  await page.getByRole("button", { name: "続行" }).click();
  await expect.poll(() => state.generateBodies.length).toBe(1);
  expect(state.generateBodies[0]).toMatchObject({
    reference_kind: "entry",
    reference_entry_id: ENTRY_ID,
    reference_type: "character",
    reference_strength: 0.85,
    reference_fidelity: 1,
    source_kind: "none",
    transparent_background: false,
  });
  const newest = page.locator(".prompt-expander__entry-list > li").first();
  await expect(newest.locator(".prompt-expander__badge").last()).toHaveText(
    "精密参照",
  );

  // 「参照にする」で生成結果を次の参照に差し替えられる（立ち絵差分の連鎖）
  await newest.getByRole("button", { name: "参照にする" }).click();
  await expect(section).toContainText("1girl, standing");
});

test("transparent background is sent with expand/generate and V4.5 entries are cut out client-side with a PNG download", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  // 生成結果は白背景の PNG（切り抜き対象）を返す。後から登録したルートが優先される
  await page.route(
    (url) =>
      url.pathname.startsWith("/api/prompt-expander/images/pe-entry-new"),
    async (route) => {
      await route.fulfill({
        body: Buffer.from(WHITE_BG_PNG_BASE64, "base64"),
        contentType: "image/png",
      });
    },
  );
  await openSession(page);

  const toggle = page.getByRole("checkbox", { name: "画像の背景を透過" });
  await expect(toggle).toBeEnabled();
  await expect(page.getByText(/V4\.5 系: 白背景で生成し/)).toBeVisible();
  await page
    .locator(".prompt-expander__switch", { hasText: "画像の背景を透過" })
    .click();
  await expect(toggle).toBeChecked();
  await expect(
    page.locator(".prompt-expander__section[data-section-id='params']"),
  ).toContainText("透過");
  // V5 では文言が切り替わる（スイッチ自体は無効化しない）
  await page.getByLabel("画像モデル").selectOption("nai-diffusion-5-full");
  await expect(
    page.getByText(/V5 系: プロンプトに transparent background/),
  ).toBeVisible();
  await expect(toggle).toBeEnabled();
  await page.getByLabel("画像モデル").selectOption("nai-diffusion-4-5-full");

  // 拡張にも生成にもフラグが載る
  await positiveField(page).fill("銀髪の少女の立ち絵");
  await positiveToolbar(page)
    .getByRole("button", { name: "LLMでプロンプト化" })
    .click();
  await expect.poll(() => state.expandBodies.length).toBe(1);
  expect(state.expandBodies[0]).toMatchObject({ transparent_background: true });
  const card = page.getByRole("region", { name: "変換結果（プロンプト）" });
  await card.getByRole("button", { name: "この内容で生成" }).click();
  await expect.poll(() => state.generateBodies.length).toBe(1);
  expect(state.generateBodies[0]).toMatchObject({
    transparent_background: true,
  });

  // エントリにはバッジが付き、画像は切り抜かれた blob URL に置き換わり、透過 PNG を保存できる
  const newest = page.locator(".prompt-expander__entry-list > li").first();
  await expect(newest.locator(".prompt-expander__badge").last()).toHaveText(
    "透過",
  );
  await expect(newest.locator(".prompt-expander__entry-image")).toHaveAttribute(
    "src",
    /^blob:/,
  );
  const download = newest.getByRole("link", { name: "透過PNGを保存" });
  await expect(download).toHaveAttribute("href", /^blob:/);
  await expect(download).toHaveAttribute("download", /\.png$/);
});

test("comic notation chips insert markers at the caret and the narration toggle is sent with expand", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  await page.getByLabel("画像モデル").selectOption("nai-diffusion-5-full");
  await page
    .locator(".prompt-expander__switch", { hasText: "漫画モード" })
    .click();
  await expect(
    page.getByRole("checkbox", { name: "漫画モード" }),
  ).toBeChecked();

  // 記法チップは漫画モード中だけ欄の上に出る
  const chips = page.getByRole("toolbar", { name: "漫画の記法を挿入" });
  await expect(chips).toBeVisible();
  await expect(page.getByText(/記法: 「セリフ」『モノローグ』/)).toBeVisible();

  const field = positiveField(page);
  await field.fill("放課後の教室");
  await field.press("End");
  // コマ番号は行頭に連番で入る（行の途中なら改行してから）
  await chips.getByRole("button", { name: "コマ番号" }).click();
  await expect(field).toHaveValue("放課後の教室\n①");
  // 括弧はカーソル位置に入り、カーソルは括弧の内側に置かれるのでそのまま打てる
  await chips.getByRole("button", { name: "セリフ" }).click();
  await page.keyboard.type("え、これ私…？");
  await expect(field).toHaveValue("放課後の教室\n①「え、これ私…？」");
  await field.press("End");
  await chips.getByRole("button", { name: "ナレーション" }).click();
  await page.keyboard.type("三日後");
  await field.press("End");
  await chips.getByRole("button", { name: "コマ番号" }).click();
  await chips.getByRole("button", { name: "効果音" }).click();
  await page.keyboard.type("ドクン");
  const instruction = "放課後の教室\n①「え、これ私…？」【三日後】\n②《ドクン》";
  await expect(field).toHaveValue(instruction);
  // 選択範囲があればそれを包む
  await field.evaluate((node: HTMLTextAreaElement) => {
    node.setSelectionRange(0, 6);
  });
  await chips.getByRole("button", { name: "モノローグ" }).click();
  await expect(field).toHaveValue(`『放課後の教室』${instruction.slice(6)}`);

  // 自動ナレーションは既定 OFF。ON にすると設定に保存され、拡張リクエストに載る
  await page.getByRole("button", { name: "漫画（コマ割り）" }).click();
  const narrationSwitch = page.getByRole("checkbox", {
    name: "ナレーション枠を自動で入れる",
  });
  await expect(narrationSwitch).not.toBeChecked();
  await page
    .locator(".prompt-expander__switch", {
      hasText: "ナレーション枠を自動で入れる",
    })
    .click();
  await expect(narrationSwitch).toBeChecked();
  await expect.poll(() => state.settings.manga_narration).toBe(true);

  await positiveToolbar(page)
    .getByRole("button", { name: "LLMでプロンプト化" })
    .click();
  await expect.poll(() => state.expandBodies.length).toBe(1);
  expect(state.expandBodies[0]).toMatchObject({
    manga_mode: true,
    instruction: `『放課後の教室』${instruction.slice(6)}`,
    manga: { narration: true },
  });
});

test("character prompt mode is remembered across reloads", async ({ page }) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  await openSession(page);

  const characterSwitch = page.getByRole("checkbox", {
    name: "キャラクタープロンプト",
  });
  await expect(characterSwitch).not.toBeChecked();
  await page
    .locator(".prompt-expander__switch", { hasText: "キャラクタープロンプト" })
    .click();
  await expect(characterSwitch).toBeChecked();
  await expect
    .poll(() =>
      page.evaluate(() =>
        localStorage.getItem("prompt_expander_character_mode"),
      ),
    )
    .toBe("true");

  await page.reload();
  await expect(positiveField(page)).toBeVisible();
  await expect(
    page.getByRole("checkbox", { name: "キャラクタープロンプト" }),
  ).toBeChecked();
});

test("draft a storyboard from the synopsis, then revert to the original text", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  await page.getByLabel("画像モデル").selectOption("nai-diffusion-5-full");
  await page
    .locator(".prompt-expander__switch", { hasText: "漫画モード" })
    .click();
  const draftButton = page.getByRole("button", {
    name: "あらすじからネームを下書き",
  });
  // 空欄では押せない
  await expect(draftButton).toBeDisabled();
  const field = positiveField(page);
  await field.fill("放課後、彼女が制服姿に変わってしまい戸惑う");
  await expect(draftButton).toBeEnabled();
  await draftButton.click();

  await expect.poll(() => state.scriptBodies.length).toBe(1);
  expect(state.scriptBodies[0]).toMatchObject({
    instruction: "放課後、彼女が制服姿に変わってしまい戸惑う",
    image_model: "nai-diffusion-5-full",
    manga: { narration: false },
  });
  const script =
    "①放課後、彼女が制服姿に変わってしまい戸惑う。彼女が鏡を見る「え…？」\n②体が変わっていく《ドクン》";
  await expect(field).toHaveValue(script);
  await expect(field).toBeEditable();
  await expect(
    page.getByText("あらすじからネームを下書きしました。", { exact: false }),
  ).toBeVisible();

  // 元の文に戻せる。戻すと案内は消える
  await page.getByRole("button", { name: "元の文に戻す" }).click();
  await expect(field).toHaveValue("放課後、彼女が制服姿に変わってしまい戸惑う");
  await expect(page.getByRole("button", { name: "元の文に戻す" })).toHaveCount(
    0,
  );
});

test("composer sections collapse, expand and persist to localStorage", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  await openSession(page);

  // 並び順: 生成パラメータ → 漫画（コマ割り） → プロンプト／指示 → キャラクタープロンプト → i2i設定 → 精密参照
  const headings = page.locator(
    ".prompt-expander__composer .prompt-expander__section-toggle",
  );
  await expect(headings).toHaveText([
    /生成パラメータ/,
    /漫画（コマ割り）/,
    /プロンプト／指示/,
    /キャラクタープロンプト/,
    /i2i設定/,
    /精密参照（V4.5 系のみ）/,
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
    panel.getByLabel("テキストモデル（プロンプト化・提案に使用）"),
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

test("restore puts the original instruction back and rebuilds the expansion card", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  const textarea = positiveField(page);
  await expect(textarea).toHaveValue("");
  await page
    .locator(".prompt-expander__entry-list > li")
    .first()
    .getByRole("button", { name: "欄へ復元" })
    .click();
  // 拡張ありのエントリ: 原文が欄に戻り、変換結果は確認カードとして再現される
  await expect(textarea).toHaveValue(ENTRY_INSTRUCTION);
  await expect(negativeField(page)).toHaveValue("lowres");
  const card = page.getByRole("region", { name: "変換結果（プロンプト）" });
  await expect(card).toBeVisible();
  await expect(card.getByLabel("ベースプロンプト")).toHaveValue(
    ENTRY_FINAL_PROMPT,
  );
  // 既定では seed は復元しない（設定の部分更新に seed を含めない）
  await expect.poll(() => state.settingsBodies.length).toBeGreaterThan(0);
  expect(state.settingsBodies.at(-1)).not.toHaveProperty("seed");

  // 再現したカードからそのまま生成すると、原文と拡張モードのメタデータが付く
  await card.getByRole("button", { name: "この内容で生成" }).click();
  await expect.poll(() => state.generateBodies.length).toBe(1);
  expect(state.generateBodies[0]).toMatchObject({
    prompt: ENTRY_FINAL_PROMPT,
    instruction: ENTRY_INSTRUCTION,
    positive_expand_mode: "tags",
  });
  expect(state.generateBodies[0]).not.toHaveProperty("seed");
});

test("restore copies the seed only after turning the setting on", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  await page
    .locator(".prompt-expander__header")
    .getByRole("button", { name: "設定", exact: true })
    .click();
  const panel = page.getByRole("region", { name: "Prompt Expander 設定" });
  const restoreSeedSwitch = panel.getByRole("checkbox", {
    name: "「欄へ復元」でシードも復元する",
  });
  await expect(restoreSeedSwitch).not.toBeChecked();
  await panel
    .locator(".prompt-expander__switch", {
      hasText: "「欄へ復元」でシードも復元する",
    })
    .click();
  await expect(restoreSeedSwitch).toBeChecked();
  await expect.poll(() => state.settings.restore_seed).toBe(true);

  await page
    .locator(".prompt-expander__entry-list > li")
    .first()
    .getByRole("button", { name: "欄へ復元" })
    .click();
  await expect.poll(() => state.settings.seed).toBe(12345);
});

test("regenerate posts the entry's prompt and settings without a seed", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  await page
    .locator(".prompt-expander__entry-list > li")
    .first()
    .getByRole("button", { name: "このプロンプトで再生成" })
    .click();
  await expect.poll(() => state.generateBodies.length).toBe(1);
  expect(state.generateBodies[0]).toMatchObject({
    prompt: ENTRY_FINAL_PROMPT,
    negative_prompt: "lowres",
    instruction: ENTRY_INSTRUCTION,
    positive_expand_mode: "tags",
    image_model: "nai-diffusion-4-5-full",
    image_size: "portrait",
    source_kind: "none",
  });
  expect(state.generateBodies[0]).not.toHaveProperty("seed");
  // 欄は変えず、生成したエントリが一覧の先頭に並ぶ
  await expect(positiveField(page)).toHaveValue("");
  await expect(page.locator(".prompt-expander__entry-list > li")).toHaveCount(
    2,
  );
});

test("entry filters narrow the list, drive the preview counter and persist", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  state.entries.push(
    entryPayload({
      id: "pe-entry-manga",
      instruction: "漫画のエントリ",
      final_prompt: "1girl, manga",
      manga_mode: true,
      manga_panel_count: 3,
      image_model: "nai-diffusion-5-full",
      image_url: "/prompt-expander/images/pe-entry-manga",
    }),
    entryPayload({
      id: "pe-entry-upload",
      kind: "uploaded",
      instruction: "アップロードしたメモ",
      positive_expand_mode: "off",
      final_prompt: "",
      image_url: "/prompt-expander/images/pe-entry-upload",
    }),
  );
  await openSession(page);

  const items = page.locator(".prompt-expander__entry-list > li");
  const filters = page.getByRole("group", { name: "履歴の絞り込み" });
  await expect(items).toHaveCount(3);
  await expect(
    filters.getByRole("button", { name: /^すべて/ }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(filters.getByRole("button", { name: /^すべて/ })).toContainText(
    "3",
  );
  await expect(filters.getByRole("button", { name: /^漫画/ })).toContainText(
    "1",
  );

  // 漫画だけに絞ると 1 件になり、選択は localStorage に残る
  await filters.getByRole("button", { name: /^漫画/ }).click();
  await expect(items).toHaveCount(1);
  await expect(items.first()).toContainText("漫画のエントリ");
  await expect
    .poll(() =>
      page.evaluate(() => localStorage.getItem("prompt_expander_entry_filter")),
    )
    .toBe("manga");

  // プレビューは絞り込み後の並びで「n / N」を出し、閉じるボタンは画面内に収まる
  await items.first().getByRole("button", { name: "画像を拡大表示" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.locator(".image-preview-modal__position")).toHaveText(
    "1 / 1",
  );
  const closeButton = dialog.getByRole("button", { name: "閉じる" });
  const box = await closeButton.boundingBox();
  const viewport = page.viewportSize();
  expect(box).not.toBeNull();
  expect(box?.y ?? -1).toBeGreaterThanOrEqual(0);
  expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(
    viewport?.width ?? 0,
  );
  await closeButton.click();
  await expect(dialog).toBeHidden();
  // 閉じた後も直前まで見ていたカードは強調されたまま
  await expect(items.first()).toHaveClass(/prompt-expander__entry--previewed/);

  await page.reload();
  await expect(positiveField(page)).toBeVisible();
  await expect(
    page
      .getByRole("group", { name: "履歴の絞り込み" })
      .getByRole("button", { name: /^漫画/ }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(items).toHaveCount(1);

  // すべてに戻すと 3 件。前後移動でカウンタと強調カードが追従する
  await page
    .getByRole("group", { name: "履歴の絞り込み" })
    .getByRole("button", { name: /^すべて/ })
    .click();
  await expect(items).toHaveCount(3);
  await items.first().getByRole("button", { name: "画像を拡大表示" }).click();
  await expect(dialog.locator(".image-preview-modal__position")).toHaveText(
    "1 / 3",
  );
  await page.keyboard.press("ArrowLeft");
  await expect(dialog.locator(".image-preview-modal__position")).toHaveText(
    "2 / 3",
  );
  await expect(items.nth(1)).toHaveClass(/prompt-expander__entry--previewed/);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(items.nth(1)).toHaveClass(/prompt-expander__entry--previewed/);
});

test("suggestions include the current input and stay after closing the modal", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  await positiveField(page).fill("カフェで働く少女");
  await positiveToolbar(page).getByRole("button", { name: "✨ 提案" }).click();
  const dialog = page.getByRole("dialog", {
    name: "メモリから好みのキャラを提案",
  });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "提案を取得" }).click();
  await expect(dialog.locator(".prompt-expander__suggest-item")).toHaveCount(2);
  // 入力欄の下書きも提案リクエストに載る
  expect(state.suggestBodies[0]).toMatchObject({
    input_text: "カフェで働く少女",
    count: 3,
  });

  // 閉じて開き直しても提案は残り、再取得は走らない
  await dialog
    .locator(".prompt-expander__modal-footer")
    .getByRole("button", { name: "閉じる" })
    .click();
  await expect(dialog).toBeHidden();
  await positiveToolbar(page).getByRole("button", { name: "✨ 提案" }).click();
  await expect(dialog).toBeVisible();
  await expect(dialog.locator(".prompt-expander__suggest-item")).toHaveCount(2);
  expect(state.suggestBodies).toHaveLength(1);

  // キャラクターモード OFF なので挿入はプロンプト欄の末尾に追記される
  await dialog
    .locator(".prompt-expander__suggest-item")
    .first()
    .getByRole("button", { name: "挿入" })
    .click();
  await expect(positiveField(page)).toHaveValue(
    "カフェで働く少女\n1girl, silver hair, blue eyes",
  );
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
