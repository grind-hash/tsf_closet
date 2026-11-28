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

type PromptExpanderEntryReferencePayload = {
  kind: "history" | "entry" | "upload" | "character";
  history_id: string | null;
  entry_id: string | null;
  character_preset_id: string | null;
  type: string;
  include_outfit: boolean | null;
  strength: number;
  fidelity: number | null;
  name: string | null;
};

type PromptExpanderEntryPayload = {
  id: string;
  session_id: string;
  kind: "generated" | "uploaded";
  instruction: string | null;
  synopsis?: string | null;
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
  references: PromptExpanderEntryReferencePayload[];
  inpaint: boolean;
  mask_url: string | null;
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
    references: [],
    inpaint: false,
    mask_url: null,
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
      transparent_background: false,
      transparent_emphasis: 2,
      use_inpaint: false,
    },
    text_model_options: [
      { id: "glm-4-6", label: "GLM 4.6" },
      { id: "xialong-v1", label: "Xialong v1" },
    ],
    image_model_options: [
      "nai-diffusion-5-full",
      "nai-diffusion-5-full-medium",
      "nai-diffusion-5-curated",
      "nai-diffusion-4-5-full",
      "nai-diffusion-4-5-curated",
    ],
    max_character_prompts: {
      "nai-diffusion-5-full": 22,
      "nai-diffusion-5-full-medium": 22,
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
  adventureEnabled?: boolean;
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
    // 画像アップロード POST の送信内容を順に記録する
    uploadBodies: [] as { image: string; instruction?: string }[],
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
      if (route.request().method() === "PATCH") {
        const body = route.request().postDataJSON() as { title: string };
        session.title = body.title;
        await route.fulfill({ json: session });
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
        synopsis?: string | null;
        positive_expand_mode: "off" | "japanese" | "tags";
        negative_expand_mode: "off" | "japanese" | "tags";
        image_model?: string;
        manga_mode?: boolean;
        manga_panel_count?: number | null;
        transparent_background?: boolean;
        references?: Array<{
          kind: PromptExpanderEntryReferencePayload["kind"];
          history_id?: string;
          entry_id?: string;
          character_preset_id?: string;
          type: string;
          include_outfit: boolean;
          strength: number;
          fidelity: number;
          name?: string;
        }>;
        transparent_emphasis?: number;
        source_kind?: "none" | "history" | "entry" | "upload";
        source_history_id?: string;
        source_entry_id?: string;
        inpaint_mask?: string;
        inpaint_mask_entry_id?: string;
      };
      state.generateBodies.push(body);
      generatedCount += 1;
      const entry = entryPayload({
        id: `pe-entry-new-${generatedCount}`,
        instruction: body.instruction ?? null,
        synopsis: body.synopsis ?? null,
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
        source_kind: body.source_kind ?? "none",
        source_history_id: body.source_history_id ?? null,
        source_entry_id: body.source_entry_id ?? null,
        inpaint: Boolean(body.inpaint_mask || body.inpaint_mask_entry_id),
        mask_url:
          body.inpaint_mask || body.inpaint_mask_entry_id
            ? `/prompt-expander/entries/pe-entry-new-${generatedCount}/mask`
            : null,
        references: (body.references ?? []).map((ref) => ({
          kind: ref.kind,
          history_id: ref.history_id ?? null,
          entry_id: ref.entry_id ?? null,
          character_preset_id: ref.character_preset_id ?? null,
          type: ref.type,
          include_outfit: null,
          strength: ref.strength,
          fidelity: ref.fidelity,
          name: ref.name ?? null,
        })),
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
  await page.route(
    (url) =>
      /^\/api\/prompt-expander\/sessions\/[^/]+\/uploads$/.test(url.pathname),
    async (route) => {
      const body = route.request().postDataJSON() as {
        image: string;
        instruction?: string;
      };
      state.uploadBodies.push(body);
      const id = `pe-entry-upload-${state.uploadBodies.length}`;
      const entry = entryPayload({
        id,
        kind: "uploaded",
        instruction: body.instruction ?? "",
        final_prompt: "",
        image_url: `/prompt-expander/images/${id}`,
      });
      state.entries.unshift(entry);
      await route.fulfill({ status: 201, json: entry });
    },
  );
  return state;
}

/** 通常プレイ(WelcomeScreen)が起動時に叩く API のモック */
async function mockGameApis(page: Page) {
  await page.route("**/api/game/characters", async (route) => {
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

/** 指示（漫画モードではあらすじ）の欄と、ネームの欄 */
function instructionField(page: Page) {
  return page.locator("#prompt-expander-instruction");
}

function scriptField(page: Page) {
  return page.locator("#prompt-expander-script");
}

function instructionToolbar(page: Page) {
  return page.getByRole("toolbar", { name: "指示欄の操作" });
}

function synopsisToolbar(page: Page) {
  return page.getByRole("toolbar", { name: "あらすじ欄の操作" });
}

function scriptToolbar(page: Page) {
  return page.getByRole("toolbar", { name: "ネーム欄の操作" });
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

test("convert the instruction into the prompt field, edit the prompt and generate", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  // 指示欄の右上: 出力形式（既定はタグ）+ プロンプト化。提案はプロンプト欄の右上
  const toolbar = instructionToolbar(page);
  await expect(toolbar.getByRole("radio", { name: "タグ" })).toBeChecked();
  await expect(
    positiveToolbar(page).getByRole("button", { name: "✨ 提案" }),
  ).toBeEnabled();
  // 空欄のうちはプロンプト化できない（理由付き）
  const expandButton = toolbar.getByRole("button", {
    name: "LLMでプロンプト化",
  });
  await expect(expandButton).toBeDisabled();
  await expect(expandButton).toHaveAttribute(
    "title",
    "プロンプト化する内容を入力してください",
  );

  const instruction = "猫耳メイドがカフェで微笑む";
  await instructionField(page).fill(instruction);
  // 欄の中で Ctrl+Enter を押すとボタンと同じくプロンプト化する
  await instructionField(page).press("Control+Enter");

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

  // 結果はプロンプト欄へ直接入り、指示はそのまま残る。確認カードは出ない
  await expect(positiveField(page)).toHaveValue(EXPANDED_PROMPT);
  await expect(instructionField(page)).toHaveValue(instruction);
  await expect(
    page.locator('label[for="prompt-expander-positive"]'),
  ).toContainText("タグで変換");
  await expect(page.getByRole("region", { name: /変換結果/ })).toHaveCount(0);

  // プロンプト欄を手直しして、そのまま生成する
  const edited = `${EXPANDED_PROMPT}, smile`;
  await positiveField(page).fill(edited);
  expect(state.generateBodies).toHaveLength(0);
  await generateButton(page).click();

  await expect.poll(() => state.generateBodies.length).toBe(1);
  expect(state.generateBodies[0]).toMatchObject({
    prompt: edited,
    instruction,
    synopsis: null,
    positive_expand_mode: "tags",
    negative_expand_mode: "off",
    image_model: "nai-diffusion-4-5-full",
  });

  // 生成したエントリが一覧の先頭に並ぶ
  const entries = page.locator(".prompt-expander__entry-list > li");
  await expect(entries).toHaveCount(2);
  await expect(entries.nth(0)).toContainText(instruction);
  await expect(entries.nth(1)).toContainText(ENTRY_INSTRUCTION);
});

test("creating the prompt again can be undone below the prompt field", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  await instructionField(page).fill("雨の日の駅で傘を差す少女");
  const expandButton = instructionToolbar(page).getByRole("button", {
    name: "LLMでプロンプト化",
  });
  await expandButton.click();
  await expect(positiveField(page)).toHaveValue(EXPANDED_PROMPT);
  // 初めて作ったときは、戻す先が無いので案内は出ない
  const rebuilt = page.locator(".prompt-expander__draft-done", {
    hasText: "プロンプトを作り直しました",
  });
  await expect(rebuilt).toHaveCount(0);

  // 手直ししたあとで作り直すと、前のプロンプトに戻せる
  await positiveField(page).fill("1girl, hand written");
  await expandButton.click();
  await expect.poll(() => state.expandBodies.length).toBe(2);
  await expect(positiveField(page)).toHaveValue(EXPANDED_PROMPT);
  await rebuilt.getByRole("button", { name: "元に戻す" }).click();
  await expect(positiveField(page)).toHaveValue("1girl, hand written");
  await expect(rebuilt).toHaveCount(0);
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
  // 指示欄は「あらすじ」になり、ネーム欄が出る。出力形式はタグ固定（理由つき）
  await expect(instructionField(page)).toHaveAttribute(
    "placeholder",
    /漫画にしたい話をざっと入力/,
  );
  await expect(scriptField(page)).toBeVisible();
  const toolbar = synopsisToolbar(page);
  await expect(toolbar.getByRole("radio", { name: "タグ" })).toBeChecked();
  await expect(toolbar.getByRole("radio", { name: "日本語文" })).toBeDisabled();
  await expect(
    page.getByText(/漫画モード中はコマ説明・外見を英語で組み立てます/).first(),
  ).toBeVisible();

  // あらすじから直接プロンプト化しても、漫画オプションが載る
  await instructionField(page).fill("男が女の子になる3コマ");
  await toolbar.getByRole("button", { name: "LLMでプロンプト化" }).click();
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
  await expect(positiveField(page)).toHaveValue(EXPANDED_PROMPT);
  await generateButton(page).click();
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
  // 漫画モードが効かないので、欄は「指示」に戻り、ネーム欄は出ない
  await expect(scriptField(page)).toHaveCount(0);
  await instructionToolbar(page)
    .getByRole("button", { name: "LLMでプロンプト化" })
    .click();
  await expect.poll(() => state.expandBodies.length).toBe(2);
  expect(state.expandBodies[1]).toMatchObject({ manga_mode: false });
  expect(state.expandBodies[1]).not.toHaveProperty("manga");
});

test("the economy V5 model warns that the negative prompt is ignored without a mask", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  const warning = page.getByText(
    /V5 Full（節約）では、マスクなしの生成にネガティブプロンプトが反映されません/,
  );
  await expect(warning).toHaveCount(0);

  await page
    .getByLabel("画像モデル")
    .selectOption("nai-diffusion-5-full-medium");
  await expect(warning).toBeVisible();
  // インペイントでは反映されるので、欄は無効化せず入力・送信できる
  await expect(negativeField(page)).toBeEditable();
  await positiveField(page).fill("1girl, raw prompt");
  await negativeField(page).fill("hat");
  await generateButton(page).click();
  await expect.poll(() => state.generateBodies.length).toBe(1);
  expect(state.generateBodies[0]).toMatchObject({
    image_model: "nai-diffusion-5-full-medium",
    negative_prompt: "hat",
  });

  await page.getByLabel("画像モデル").selectOption("nai-diffusion-5-full");
  await expect(warning).toHaveCount(0);
});

test("precise reference is off in economy mode, needs an image and an Anlas confirm, and is sent with generate", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  // 生成バーにも同名のチップがあるため、入力欄の側の見出しに絞る
  const heading = page
    .locator(".prompt-expander__composer")
    .getByRole("button", { name: "精密参照", exact: true });
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

  // V5 Full の節約モードでは無効になり理由が出る（設定は保持される）
  await page
    .getByLabel("画像モデル")
    .selectOption("nai-diffusion-5-full-medium");
  await expect(toggle).toBeDisabled();
  await expect(section).toContainText("節約モードでは無効");
  await expect(
    page.getByText(/V5 Full の節約モードでは精密参照は使えません/),
  ).toBeVisible();
  await page.getByLabel("画像モデル").selectOption("nai-diffusion-4-5-full");
  await expect(toggle).toBeEnabled();

  // トグル ON にしても参照画像が無ければ有効にならない
  await section
    .locator(".prompt-expander__switch", { hasText: "精密参照を使う" })
    .click();
  await expect(toggle).toBeChecked();
  await expect(section).toContainText("参照画像を選ぶと有効になります");

  // 画像一覧から参照画像を足す（i2i 元は空のまま）。種別・強度は画像ごとのカードで決める
  await section.getByRole("button", { name: "一覧から選ぶ" }).click();
  const picker = page.getByRole("dialog", { name: "参照画像を選ぶ" });
  await expect(picker).toBeVisible();
  await picker.locator(".prompt-expander__entry-grid-item").first().click();
  await expect(picker).toBeHidden();
  const card = section.getByTestId("prompt-expander-reference-card");
  await expect(card).toHaveCount(1);
  await expect(section).toContainText("1 枚 · +5 Anlas");
  // 名前を付けると、プロンプト欄の上に登場人物のチップが出て、押すと精密参照の欄へ移れる
  await card.getByLabel("登場人物の名前（任意）").fill("サクラ");
  const castChips = page.getByRole("group", { name: "登場人物:" });
  await expect(castChips.getByRole("button", { name: "サクラ" })).toBeVisible();
  await castChips.getByRole("button", { name: "サクラ" }).click();
  await expect(heading).toHaveAttribute("aria-expanded", "true");
  await expect(section).toBeInViewport();
  await expect(section).toContainText("1 / 6 枚");
  // V4.5 では衣装の種別は選べない
  await expect(card.getByRole("radio", { name: "衣装" })).toBeDisabled();
  await expect(card.getByLabel(/参照強度/)).toHaveAttribute("max", "1");
  // V5 Full では衣装の種別と「衣装も参照する」が操作でき、強度は 5.0 まで
  await page.getByLabel("画像モデル").selectOption("nai-diffusion-5-full");
  await expect(card.getByRole("radio", { name: "衣装" })).toBeEnabled();
  await expect(
    card.getByRole("checkbox", { name: "衣装も参照する" }),
  ).toBeEnabled();
  await expect(card.getByLabel(/参照強度/)).toHaveAttribute("max", "5");
  await page.getByLabel("画像モデル").selectOption("nai-diffusion-4-5-full");
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
  await expect(
    page.getByText(/精密参照画像 1 枚の使用により、5 Anlas/),
  ).toBeVisible();
  expect(state.generateBodies).toHaveLength(0);
  await page.getByRole("button", { name: "続行" }).click();
  await expect.poll(() => state.generateBodies.length).toBe(1);
  expect(state.generateBodies[0]).toMatchObject({
    references: [
      {
        kind: "entry",
        entry_id: ENTRY_ID,
        type: "character",
        include_outfit: false,
        strength: 0.85,
        fidelity: 1,
      },
    ],
    source_kind: "none",
    transparent_background: false,
  });
  const newest = page.locator(".prompt-expander__entry-list > li").first();
  await expect(newest.locator(".prompt-expander__badge").last()).toHaveText(
    "精密参照",
  );

  // 「参照にする」で生成結果を参照に足せる（立ち絵差分の連鎖）。押し直すと外れる
  await newest.getByRole("button", { name: "参照にする" }).click();
  await expect(card).toHaveCount(2);
  await expect(section).toContainText("1girl, standing");
  await newest.getByRole("button", { name: "参照から外す" }).click();
  await expect(card).toHaveCount(1);
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

  // 欄の下のプレビューに、送信時へ実際に足されるタグが強調付きで出る
  // （最終プロンプトには保存されないので、ここでしか確認できない）
  const tail = page.locator(".prompt-expander__transparent-tail-tags").first();
  await expect(tail).toHaveText(
    "{{simple background}}, {{white background}}, no shadow",
  );
  const emphasis = page.locator(
    ".prompt-expander__section[data-section-id='params'] .prompt-expander__radio",
  );
  await emphasis.filter({ hasText: "なし" }).click();
  await expect(page.getByRole("radio", { name: "なし" })).toBeChecked();
  await expect(tail).toHaveText(
    "simple background, white background, no shadow",
  );
  await emphasis.filter({ hasText: "{{ }}" }).first().click();
  await expect(tail).toHaveText(
    "{{simple background}}, {{white background}}, no shadow",
  );

  // 拡張にも生成にもフラグが載る
  await instructionField(page).fill("銀髪の少女の立ち絵");
  await instructionToolbar(page)
    .getByRole("button", { name: "LLMでプロンプト化" })
    .click();
  await expect.poll(() => state.expandBodies.length).toBe(1);
  expect(state.expandBodies[0]).toMatchObject({ transparent_background: true });
  await expect(positiveField(page)).toHaveValue(EXPANDED_PROMPT);
  await generateButton(page).click();
  await expect.poll(() => state.generateBodies.length).toBe(1);
  expect(state.generateBodies[0]).toMatchObject({
    transparent_background: true,
    transparent_emphasis: 2,
  });

  // 欄に既に入っているタグは二重に足さない（backend の merge_tags と同じ判定）
  await positiveField(page).fill("1girl, white background");
  await expect(tail).toHaveText("{{simple background}}, no shadow");

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

test("inpaint sends the drawn mask with the i2i source and the entry can be regenerated with it", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  // マスク一覧（通常ゲームと共用の API）と、i2i 元に使う既存エントリの画像
  await page.route("**/api/game/masks", async (route) => {
    await route.fulfill({
      json: {
        system: [
          {
            id: "system:system_mask_upper_body.png",
            name: "上半身マスク（頭部以外）",
            type: "system",
            url: "/api/game/masks/system/system_mask_upper_body.png",
          },
        ],
        history: [],
        presets: [],
      },
    });
  });
  await page.route("**/api/game/masks/system/**", async (route) => {
    await route.fulfill({
      body: Buffer.from(WHITE_BG_PNG_BASE64, "base64"),
      contentType: "image/png",
    });
  });
  await page.route("**/api/prompt-expander/images/**", async (route) => {
    await route.fulfill({
      body: Buffer.from(WHITE_BG_PNG_BASE64, "base64"),
      contentType: "image/png",
    });
  });
  await openSession(page);

  const section = page.locator(
    ".prompt-expander__section[data-section-id='inpaint']",
  );
  await section
    .getByRole("button", { name: "インペイント（部分修正）" })
    .click();

  // 元画像が無いうちは「マスクを編集」を押せず、理由が本文にも出る
  await expect(
    section.getByRole("button", { name: "マスクを編集" }),
  ).toBeDisabled();
  await expect(section).toContainText("元画像を選んでください");

  // 履歴のエントリを i2i 元にすると押せるようになる（ベース画像は i2i 元と共用）
  await page
    .locator(".prompt-expander__entry-list > li")
    .first()
    .getByRole("button", { name: "i2i元にする" })
    .click();
  const editMask = section.getByRole("button", { name: "マスクを編集" });
  await expect(editMask).toBeEnabled();

  // 定型マスクを選んで確定する（描画キャンバスは Playwright で塗らずプリセットで代用）
  await editMask.click();
  const modal = page.getByRole("dialog", { name: "マスクを編集" });
  await modal.getByRole("button", { name: "上半身マスク（頭部以外）" }).click();
  await modal.getByRole("button", { name: "このマスクを使う" }).click();
  await expect(modal).toBeHidden();
  await expect(section).toContainText("上半身マスク（頭部以外）");

  // トグルが OFF の間はマスクを送らない
  await positiveField(page).fill("1girl, smiling");
  await generateButton(page).click();
  await expect.poll(() => state.generateBodies.length).toBe(1);
  expect(state.generateBodies[0].inpaint_mask).toBeUndefined();

  // ON にすると mask が載り、i2i 元も一緒に送られる
  await section
    .locator(".prompt-expander__switch", { hasText: "インペイントを使う" })
    .click();
  await expect(
    page.getByRole("checkbox", { name: "インペイントを使う" }),
  ).toBeChecked();
  await generateButton(page).click();
  await expect.poll(() => state.generateBodies.length).toBe(2);
  const body = state.generateBodies[1];
  expect(String(body.inpaint_mask)).toMatch(/^data:image\/png;base64,/);
  expect(body.source_kind).toBe("entry");

  // エントリにバッジが付き、「このプロンプトで再生成」は同じマスクを ID で送り直す
  const newest = page.locator(".prompt-expander__entry-list > li").first();
  await expect(newest).toContainText("インペイント");
  await newest.getByRole("button", { name: "このプロンプトで再生成" }).click();
  await expect.poll(() => state.generateBodies.length).toBe(3);
  expect(state.generateBodies[2]).toMatchObject({
    inpaint_mask_entry_id: "pe-entry-new-2",
    source_kind: "entry",
  });
});

test("the workspace offers a way back to the session list", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  await openSession(page);

  // セクションの並び: 登場人物（精密参照）はキャラクタープロンプトの直後、画像の加工（i2i・インペイント）は後ろ
  const order = await page
    .locator(".prompt-expander__composer > .prompt-expander__section")
    .evaluateAll((sections) =>
      sections.map((el) => el.getAttribute("data-section-id")),
    );
  expect(order).toEqual([
    "params",
    "manga",
    "prompt",
    "characters",
    "reference",
    "i2i",
    "inpaint",
  ]);

  // 生成バーの要約チップを押すと、その設定のセクションが開いてそこへ移る
  const bar = page.getByRole("toolbar", { name: "生成操作" });
  const paramsSection = page.locator(
    ".prompt-expander__section[data-section-id='params']",
  );
  await page
    .getByRole("button", { name: "生成パラメータ", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "生成パラメータ", exact: true }),
  ).toHaveAttribute("aria-expanded", "false");
  await bar
    .getByRole("button", { name: "NAI Diffusion V4.5 Full", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "生成パラメータ", exact: true }),
  ).toHaveAttribute("aria-expanded", "true");
  await expect(paramsSection).toBeInViewport();

  // Anlas はスクロールで隠れない下端の生成バーに出し、作業中の見出しには出さない
  await expect(page.getByRole("toolbar", { name: "生成操作" })).toContainText(
    "Anlas: 100",
  );
  await expect(page.locator(".prompt-expander__header")).not.toContainText(
    "Anlas",
  );

  // 作業中はどのセッションを開いているかが分かり、一覧へ戻れる
  const header = page.locator(".prompt-expander__header");
  await expect(header).toContainText("テストセッション");
  await header.getByRole("button", { name: "← 一覧へ戻る" }).click();

  await expect(page).toHaveURL(/\/prompt-expander$/);
  await expect(
    page.getByLabel("新しいセッションのタイトル（省略可）"),
  ).toBeVisible();
  // 一覧では戻るボタンを出さない
  await expect(page.getByRole("button", { name: "← 一覧へ戻る" })).toHaveCount(
    0,
  );

  // サイドメニューの項目は詳細ページでも選択中として扱う
  await openSession(page);
  await expect(
    page.getByRole("button", { name: /Prompt Expander/ }).first(),
  ).toHaveAttribute("aria-current", "page");
});

test("the generate control bar stays visible, summarises the settings and toggles every section", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  await openSession(page);

  // 生成ボタンはコンポーザ内ではなく下端のコントロールエリアにあり、1 つだけ
  const bar = page.getByRole("toolbar", { name: "生成操作" });
  await expect(generateButton(page)).toHaveCount(1);
  await expect(
    bar.getByRole("button", { name: "生成", exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".prompt-expander__composer .prompt-expander__generate"),
  ).toHaveCount(0);

  // 現在値のサマリが出る（モデルとサイズは常に、透過は ON のときだけ）
  await expect(bar).toContainText("NAI Diffusion V4.5 Full");
  await expect(bar).toContainText("縦長");
  await expect(bar).not.toContainText("透過");
  await page
    .locator(".prompt-expander__switch", { hasText: "画像の背景を透過" })
    .click();
  await expect(bar).toContainText("透過");

  // 全セクションを開いても生成ボタンは画面内に留まる
  await bar.getByRole("button", { name: "すべて開く" }).click();
  const headings = page.locator(
    ".prompt-expander__composer .prompt-expander__section-toggle",
  );
  const count = await headings.count();
  for (let i = 0; i < count; i += 1) {
    await expect(headings.nth(i)).toHaveAttribute("aria-expanded", "true");
  }
  await expect(
    bar.getByRole("button", { name: "生成", exact: true }),
  ).toBeInViewport();

  // 「すべて閉じる」で畳め、状態は localStorage に残る
  await bar.getByRole("button", { name: "すべて閉じる" }).click();
  for (let i = 0; i < count; i += 1) {
    await expect(headings.nth(i)).toHaveAttribute("aria-expanded", "false");
  }
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

  // 記法チップは漫画モード中だけ、ネーム欄の上に出る
  const chips = page.getByRole("toolbar", { name: "漫画の記法を挿入" });
  await expect(chips).toBeVisible();
  await expect(page.getByText(/記法: 「セリフ」『モノローグ』/)).toBeVisible();

  const field = scriptField(page);
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

  await scriptToolbar(page)
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

test("draft a storyboard from the synopsis into the storyboard field, then undo it", async ({
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
  // 作業の順に、ネーム下書きはあらすじ欄のツールバーでプロンプト化の左に並ぶ
  const labels = await synopsisToolbar(page)
    .getByRole("button")
    .allInnerTexts();
  expect(labels.indexOf("あらすじからネームを下書き")).toBeGreaterThanOrEqual(
    0,
  );
  expect(labels.indexOf("あらすじからネームを下書き")).toBeLessThan(
    labels.indexOf("LLMでプロンプト化"),
  );
  // 空欄では押せない
  await expect(draftButton).toBeDisabled();
  const synopsis = "放課後、彼女が制服姿に変わってしまい戸惑う";
  await instructionField(page).fill(synopsis);
  await expect(draftButton).toBeEnabled();
  await draftButton.click();

  await expect.poll(() => state.scriptBodies.length).toBe(1);
  expect(state.scriptBodies[0]).toMatchObject({
    instruction: synopsis,
    image_model: "nai-diffusion-5-full",
    manga: { narration: false },
  });
  const script = `①${synopsis}。彼女が鏡を見る「え…？」\n②体が変わっていく《ドクン》`;
  // ネームはネーム欄へ入り、あらすじは残る
  await expect(scriptField(page)).toHaveValue(script);
  await expect(scriptField(page)).toBeEditable();
  await expect(instructionField(page)).toHaveValue(synopsis);
  const drafted = page.locator(".prompt-expander__draft-done", {
    hasText: "ネームを下書きしました。",
  });
  await expect(drafted).toBeVisible();

  // 元に戻すと、下書き前のネーム（ここでは空）に戻り、案内は消える
  await drafted.getByRole("button", { name: "元に戻す" }).click();
  await expect(scriptField(page)).toHaveValue("");
  await expect(drafted).toHaveCount(0);
  await expect(instructionField(page)).toHaveValue(synopsis);
});

test("composer sections collapse, expand and persist to localStorage", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  await openSession(page);

  // 並び順: 生成パラメータ → 漫画（コマ割り） → プロンプト → キャラクタープロンプト
  //         → 精密参照（登場人物） → i2i設定 → インペイント（部分修正）
  const headings = page.locator(
    ".prompt-expander__composer .prompt-expander__section-toggle",
  );
  await expect(headings).toHaveText([
    /生成パラメータ/,
    /漫画（コマ割り）/,
    /▾プロンプト$/,
    /キャラクタープロンプト/,
    /精密参照/,
    /i2i設定/,
    /インペイント（部分修正）/,
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

test("restore puts the instruction and the prompt back into their own fields", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  await expect(positiveField(page)).toHaveValue("");
  await page
    .locator(".prompt-expander__entry-list > li")
    .first()
    .getByRole("button", { name: "欄へ復元" })
    .click();
  // 拡張ありのエントリ: 指示は指示欄、最終プロンプトはプロンプト欄へ戻る
  await expect(instructionField(page)).toHaveValue(ENTRY_INSTRUCTION);
  await expect(positiveField(page)).toHaveValue(ENTRY_FINAL_PROMPT);
  await expect(negativeField(page)).toHaveValue("lowres");
  await expect(page.getByRole("region", { name: /変換結果/ })).toHaveCount(0);
  // 既定では seed は復元しない（設定の部分更新に seed を含めない）
  await expect.poll(() => state.settingsBodies.length).toBeGreaterThan(0);
  expect(state.settingsBodies.at(-1)).not.toHaveProperty("seed");

  // そのまま生成すると、元の指示と拡張モードのメタデータが付く
  await generateButton(page).click();
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

test("make a character turns the entry image into a character portrait", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  const preset = {
    id: "preset-new",
    name: "新しいキャラクター",
    appearance_natural: "",
    appearance_tags: ENTRY_FINAL_PROMPT,
    default_position: "center",
    negative_tags: "",
    profile: null,
    thumbnail_url: null,
    avatar_model_id: null,
    voice: null,
    portrait_url: "/game/character-presets/preset-new/images/source-1.png",
    salon_enabled: true,
    created_at: "2026-11-25T00:00:00",
    updated_at: "2026-11-25T00:00:00",
  };
  const createBodies: Record<string, unknown>[] = [];
  const importBodies: Record<string, unknown>[] = [];
  await page.route("**/api/game/character-presets", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    createBodies.push(route.request().postDataJSON());
    await route.fulfill({
      status: 201,
      json: { ...preset, appearance_tags: "", portrait_url: null },
    });
  });
  await page.route(
    "**/api/game/character-presets/preset-new/portrait/from-source",
    async (route) => {
      importBodies.push(route.request().postDataJSON());
      await route.fulfill({
        json: {
          preset,
          source: {
            name: null,
            appearance_natural: "",
            appearance_tags: ENTRY_FINAL_PROMPT,
          },
        },
      });
    },
  );
  await page.route(
    "**/api/game/character-presets/preset-new",
    async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      await route.fulfill({ json: preset });
    },
  );
  await openSession(page);

  await page
    .locator(".prompt-expander__entry-list > li")
    .first()
    .getByRole("button", { name: "キャラクターにする" })
    .click();

  // 作ったキャラクターの編集画面へ移る
  await expect(page).toHaveURL(/\/characters\/preset-new$/);
  expect(createBodies).toHaveLength(1);
  expect(importBodies).toEqual([{ prompt_expander_entry_id: ENTRY_ID }]);
});

test("new play has no own-image section", async ({ page }) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockGameApis(page);
  await page.goto("/play/new");
  const welcome = page.locator(".welcome-screen");
  await expect(welcome).toBeVisible();
  // 自分の画像はキャラクター画面から始める
  await expect(
    welcome.getByRole("link", { name: "キャラクター画面を開く" }),
  ).toBeVisible();
  await expect(
    welcome.getByRole("button", { name: "Prompt Expander から選択" }),
  ).toHaveCount(0);
  await expect(welcome.getByPlaceholder(/外見タグ/)).toHaveCount(0);
});

test("adventure setup can start from a Prompt Expander entry", async ({
  page,
}) => {
  await enableFeatures(page, {
    experimentalPromptExpanderEnabled: true,
    adventureEnabled: true,
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
    adventureEnabled: true,
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
    adventureEnabled: true,
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

// 画面全体へのドロップ用: PNG 1 枚を含む DataTransfer をブラウザ側で作る
async function createImageDataTransfer(page: Page, name: string) {
  return page.evaluateHandle(
    ({ fileName, base64 }) => {
      const raw = base64.replace(/^data:[^,]*,/, "");
      const bytes = Uint8Array.from(atob(raw), (c) => c.charCodeAt(0));
      const transfer = new DataTransfer();
      transfer.items.add(new File([bytes], fileName, { type: "image/png" }));
      return transfer;
    },
    { fileName: name, base64: WHITE_BG_PNG_BASE64 },
  );
}

// 画面（メインコンテンツ）へ画像をドロップし、使い道ダイアログを返す
async function dropImageOnScreen(page: Page, name: string) {
  const overlay = page.getByTestId("prompt-expander-drop-overlay");
  const content = page.locator(".main-layout__content");
  const dataTransfer = await createImageDataTransfer(page, name);
  await content.dispatchEvent("dragenter", { dataTransfer });
  await expect(overlay).toBeVisible();
  await expect(overlay).toContainText("ドロップして画像を使う");
  await content.dispatchEvent("dragover", { dataTransfer });
  await content.dispatchEvent("drop", { dataTransfer });
  await dataTransfer.dispose();
  await expect(overlay).toBeHidden();
  const dialog = page.getByRole("dialog", {
    name: "この画像で何をしたいですか？",
  });
  await expect(dialog).toBeVisible();
  await expect(
    dialog.locator(".prompt-expander__upload-preview"),
  ).toBeVisible();
  await expect(dialog).toContainText(name);
  return dialog;
}

test("dropping an image anywhere asks what to use it for; i2i source uploads it and reveals the section", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  // i2i セクションを閉じた状態から始め、ドロップ後に開くことを確認する
  const heading = page.getByRole("button", { name: "i2i設定" });
  if ((await heading.getAttribute("aria-expanded")) === "true") {
    await heading.click();
  }
  await expect(heading).toHaveAttribute("aria-expanded", "false");

  const dialog = await dropImageOnScreen(page, "dropped-i2i.png");
  await dialog.getByRole("button", { name: /^i2i元にする/ }).click();
  await expect(dialog).toBeHidden();

  // 既定は「履歴に残す」ON なのでアップロード API に送られ、i2i 元に入る
  await expect.poll(() => state.uploadBodies.length).toBe(1);
  expect(state.uploadBodies[0].image).toMatch(/^data:image\/png;base64,/);
  await expect(heading).toHaveAttribute("aria-expanded", "true");
  const section = page.locator(
    ".prompt-expander__section[data-section-id='i2i']",
  );
  await expect(section).toContainText("dropped-i2i.png");
  await expect(section).toBeInViewport();
  // 履歴一覧の先頭にアップロード分が増える
  await expect(page.locator(".prompt-expander__entry-list > li")).toHaveCount(
    2,
  );
});

test("dropping an image and choosing inpaint turns inpaint on and opens the mask editor", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  const heading = page.getByRole("button", {
    name: "インペイント（部分修正）",
  });
  await expect(heading).toHaveAttribute("aria-expanded", "false");

  const dialog = await dropImageOnScreen(page, "dropped-inpaint.png");
  await dialog.getByRole("button", { name: /^インペイントの元にする/ }).click();
  await expect(dialog).toBeHidden();

  // インペイントが ON になり、続けてマスク編集モーダルが開く
  await expect
    .poll(() => state.settingsBodies.some((b) => b.use_inpaint === true))
    .toBe(true);
  const maskDialog = page.getByRole("dialog", { name: "マスクを編集" });
  await expect(maskDialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(maskDialog).toBeHidden();

  await expect(heading).toHaveAttribute("aria-expanded", "true");
  const section = page.locator(
    ".prompt-expander__section[data-section-id='inpaint']",
  );
  await expect(section).toContainText("dropped-inpaint.png");
  await expect(section).toBeInViewport();
});

test("dropping an image and choosing precise reference is off in economy mode and turns the reference on", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  // V5 Full の節約モードでは精密参照の選択肢が無効になり理由が出る
  await page
    .getByLabel("画像モデル")
    .selectOption("nai-diffusion-5-full-medium");
  let dialog = await dropImageOnScreen(page, "dropped-ref.png");
  const referenceChoice = dialog.getByRole("button", {
    name: /^精密参照にする/,
  });
  await expect(referenceChoice).toBeDisabled();
  await expect(dialog).toContainText("節約モード");
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  // V4.5 に戻すと選べる。「履歴に残す」を OFF にして参照だけに入れる
  await page.getByLabel("画像モデル").selectOption("nai-diffusion-4-5-full");
  dialog = await dropImageOnScreen(page, "dropped-ref.png");
  await dialog
    .locator(".prompt-expander__switch", { hasText: "履歴に残す" })
    .click();
  await dialog.getByRole("button", { name: /^精密参照にする/ }).click();
  await expect(dialog).toBeHidden();

  expect(state.uploadBodies).toHaveLength(0);
  await expect
    .poll(() =>
      state.settingsBodies.some((b) => b.use_precise_reference === true),
    )
    .toBe(true);
  // 生成バーにも同名のチップがあるため、入力欄の側の見出しに絞る
  const heading = page
    .locator(".prompt-expander__composer")
    .getByRole("button", { name: "精密参照", exact: true });
  await expect(heading).toHaveAttribute("aria-expanded", "true");
  const section = page.locator(
    ".prompt-expander__section[data-section-id='reference']",
  );
  await expect(section).toContainText("dropped-ref.png");
  await expect(
    page.getByRole("checkbox", { name: "精密参照を使う" }),
  ).toBeChecked();
  await expect(section).toBeInViewport();
});

test("generation shortcuts stay blocked while the API key consent dialog is open", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  // 同意がまだの状態で開く（enableFeatures は同意済みにしているので、その後で消す）
  await page.addInitScript(() => {
    window.localStorage.removeItem("novelai_api_key_consent");
  });
  await page.goto(`/prompt-expander/${SESSION_ID}`);
  const dialog = page.getByRole("dialog", { name: "APIキーの利用について" });
  await expect(dialog).toBeVisible();
  // 同意ボタンにフォーカスがあり、背後の入力欄へは移れない
  await expect(
    dialog.getByRole("button", { name: "同意して続行" }),
  ).toBeFocused();
  await expect(positiveField(page)).not.toBeFocused();
  await positiveField(page)
    .focus()
    .catch(() => {});
  await expect(positiveField(page)).not.toBeFocused();
  // 生成のショートカットを押しても生成リクエストは飛ばない
  await page.keyboard.press("Control+Shift+Enter");
  await page.waitForTimeout(300);
  expect(state.generateBodies).toHaveLength(0);
});

test("the generate bar shows the result, clears a hiding filter and moves to the new entry", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  // 新着が隠れる絞り込み（アップロード）にしておく
  await page
    .getByRole("group", { name: "履歴の絞り込み" })
    .getByRole("button", { name: /アップロード/ })
    .click();

  await positiveField(page).fill("1girl, standing");
  await generateButton(page).click();
  await expect.poll(() => state.generateBodies.length).toBe(1);

  const bar = page.getByRole("toolbar", { name: "生成操作" });
  await expect(bar).toContainText("生成しました");
  await bar.getByRole("button", { name: "結果を見る" }).click();
  // 絞り込みが「すべて」に戻り、新着のカードへ移ってフォーカスが入る
  const newest = page.locator('[data-entry-id="pe-entry-new-1"]');
  await expect(newest).toBeVisible();
  await expect(
    newest.locator(".prompt-expander__entry-image-btn"),
  ).toBeFocused();
  // 閉じると消える
  await bar.getByRole("button", { name: "閉じる" }).click();
  await expect(bar).not.toContainText("生成しました");
});

test("chips move keyboard focus to the section heading", async ({ page }) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  await openSession(page);
  const bar = page.getByRole("toolbar", { name: "生成操作" });
  await bar
    .getByRole("button", { name: "NAI Diffusion V4.5 Full", exact: true })
    .press("Enter");
  await expect(
    page
      .locator(".prompt-expander__composer")
      .getByRole("button", { name: "生成パラメータ", exact: true }),
  ).toBeFocused();
});

test("the workspace becomes one column when the settings panel narrows it", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  await page.setViewportSize({ width: 1101, height: 900 });
  await openSession(page);
  const columns = () =>
    page
      .locator(".prompt-expander__workspace")
      .evaluate(
        (el) => getComputedStyle(el).gridTemplateColumns.split(" ").length,
      );
  // 設定パネルを閉じていれば 2 列
  expect(await columns()).toBe(2);
  // 設定パネルを開くと作業域が狭くなるので 1 列
  await page
    .locator(".prompt-expander__header")
    .getByRole("button", { name: "設定" })
    .click();
  await expect.poll(columns).toBe(1);
});

test("the session can be renamed from the workspace header", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  await openSession(page);
  const header = page.locator(".prompt-expander__header");
  await header.getByRole("button", { name: "名前変更" }).click();
  const input = header.getByLabel("セッション名");
  await expect(input).toBeFocused();
  // Esc で閉じる
  await input.press("Escape");
  await expect(header.getByLabel("セッション名")).toHaveCount(0);
  await expect(header).toContainText("テストセッション");
  // Enter で保存すると、見出しと生成履歴の題名が変わる
  await header.getByRole("button", { name: "名前変更" }).click();
  await header.getByLabel("セッション名").fill("改名したセッション");
  await header.getByLabel("セッション名").press("Enter");
  await expect(header).toContainText("改名したセッション");
  await expect(header.getByLabel("セッション名")).toHaveCount(0);
});

test("notifications sit above the generate bar instead of over the header buttons", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  await page.route(
    (url) => url.pathname.endsWith("/generate"),
    async (route) => {
      await route.fulfill({
        status: 502,
        json: { detail: { code: "image_failed", message: "timeout" } },
      });
    },
  );
  await openSession(page);
  await positiveField(page).fill("1girl, standing");
  await generateButton(page).click();
  const toast = page.locator(".notification-toast").first();
  await expect(toast).toBeVisible();
  const toastBox = await toast.boundingBox();
  const barBox = await page
    .getByRole("toolbar", { name: "生成操作" })
    .boundingBox();
  const settingsBox = await page
    .locator(".prompt-expander__header")
    .getByRole("button", { name: "設定" })
    .boundingBox();
  expect(toastBox && barBox && settingsBox).toBeTruthy();
  if (!toastBox || !barBox || !settingsBox) return;
  // 生成バーより上で、見出しの設定ボタンとは重ならない
  expect(toastBox.y + toastBox.height).toBeLessThanOrEqual(barBox.y);
  expect(toastBox.y).toBeGreaterThan(settingsBox.y + settingsBox.height);
  // 見出しの設定ボタンは押せる
  await page
    .locator(".prompt-expander__header")
    .getByRole("button", { name: "設定" })
    .click();
});

test("an entry can be set and cleared as the i2i source, and the generate bar shows it", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  await openSession(page);
  const entry = page.locator(".prompt-expander__entry-list > li").first();
  const bar = page.getByRole("toolbar", { name: "生成操作" });
  await expect(bar.getByRole("button", { name: "i2i元あり" })).toHaveCount(0);
  await entry.getByRole("button", { name: "i2i元にする" }).click();
  // 選ぶと「解除」に変わり、生成バーにも出る
  await expect(
    entry.getByRole("button", { name: "i2i元を解除" }),
  ).toBeVisible();
  await expect(bar.getByRole("button", { name: "i2i元あり" })).toBeVisible();
  await entry.getByRole("button", { name: "i2i元を解除" }).click();
  await expect(
    entry.getByRole("button", { name: "i2i元にする" }),
  ).toBeVisible();
  await expect(bar.getByRole("button", { name: "i2i元あり" })).toHaveCount(0);
});

test("the prompt field tells when the instruction changed after creating the prompt", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);
  await instructionField(page).fill("赤いドレスの女の子");
  await instructionToolbar(page)
    .getByRole("button", { name: "LLMでプロンプト化" })
    .click();
  await expect(positiveField(page)).toHaveValue(EXPANDED_PROMPT);
  const notice = page.locator(".prompt-expander__draft-done", {
    hasText: "プロンプトを作ったあとで指示を変更しました",
  });
  await expect(notice).toHaveCount(0);
  // 指示だけ直すと、プロンプト欄の下に案内と作り直しが出る
  await instructionField(page).fill("青いドレスの女の子");
  await expect(notice).toBeVisible();
  await notice.getByRole("button", { name: "いまの指示で作り直す" }).click();
  await expect.poll(() => state.expandBodies.length).toBe(2);
  expect(state.expandBodies[1]).toMatchObject({
    instruction: "青いドレスの女の子",
  });
  await expect(notice).toHaveCount(0);
});

test("comic mode keeps the synopsis, storyboard and prompt apart and restores all three", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);
  await page.getByLabel("画像モデル").selectOption("nai-diffusion-5-full");
  await page
    .locator(".prompt-expander__switch", { hasText: "漫画モード" })
    .click();
  const synopsis = "放課後、彼女が制服姿に変わってしまい戸惑う";
  await instructionField(page).fill(synopsis);
  await page
    .getByRole("button", { name: "あらすじからネームを下書き" })
    .click();
  await expect(scriptField(page)).not.toHaveValue("");
  // ネームを手直ししても、あらすじはそのまま見える
  await scriptField(page).press("End");
  await scriptField(page).type("！");
  const script = await scriptField(page).inputValue();
  await expect(instructionField(page)).toHaveValue(synopsis);

  // ネームからプロンプトを作って生成すると、ネームとあらすじが分けて送られる
  await scriptToolbar(page)
    .getByRole("button", { name: "LLMでプロンプト化" })
    .click();
  await expect.poll(() => state.expandBodies.length).toBe(1);
  expect(state.expandBodies[0]).toMatchObject({ instruction: script });
  await expect(positiveField(page)).toHaveValue(EXPANDED_PROMPT);
  await generateButton(page).click();
  await expect.poll(() => state.generateBodies.length).toBe(1);
  expect(state.generateBodies[0]).toMatchObject({
    instruction: script,
    synopsis,
  });

  // 欄を書き換えてから新しいエントリを復元すると、3 つの欄がそれぞれ戻る
  await instructionField(page).fill("別のあらすじ");
  await scriptField(page).fill("");
  await positiveField(page).fill("");
  await page
    .locator(".prompt-expander__entry-list > li")
    .first()
    .getByRole("button", { name: "欄へ復元" })
    .click();
  await expect(instructionField(page)).toHaveValue(synopsis);
  await expect(scriptField(page)).toHaveValue(script);
  await expect(positiveField(page)).toHaveValue(EXPANDED_PROMPT);
});

test("writing directly shows only the prompt field and is remembered", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  await openSession(page);

  const modes = page.getByRole("radiogroup", { name: "プロンプトの入れ方" });
  await expect(modes.getByRole("radio", { name: "LLMで作る" })).toBeChecked();
  await expect(instructionField(page)).toBeVisible();
  await instructionField(page).fill("書きかけの指示");

  // 直接書くと、指示の欄は隠れ、プロンプト欄だけで生成できる
  await modes
    .locator(".prompt-expander__radio", { hasText: "直接書く" })
    .click();
  await expect(modes.getByRole("radio", { name: "直接書く" })).toBeChecked();
  await expect(instructionField(page)).toHaveCount(0);
  await positiveField(page).fill("1girl, maid, cafe");
  await generateButton(page).click();
  await expect.poll(() => state.generateBodies.length).toBe(1);
  expect(state.generateBodies[0]).toMatchObject({
    prompt: "1girl, maid, cafe",
    instruction: null,
    positive_expand_mode: "off",
  });

  // 再読み込みしても選んだ入れ方は残る
  await page.reload();
  await expect(positiveField(page)).toBeVisible();
  await expect(
    page
      .getByRole("radiogroup", { name: "プロンプトの入れ方" })
      .getByRole("radio", { name: "直接書く" }),
  ).toBeChecked();
  await expect(instructionField(page)).toHaveCount(0);

  // LLM で作ったエントリを復元すると、戻した指示が見えるよう「LLMで作る」へ切り替わる
  await page
    .locator(".prompt-expander__entry-list > li")
    .filter({ hasText: ENTRY_INSTRUCTION })
    .first()
    .getByRole("button", { name: "欄へ復元" })
    .click();
  await expect(instructionField(page)).toHaveValue(ENTRY_INSTRUCTION);
  await expect(
    page
      .getByRole("radiogroup", { name: "プロンプトの入れ方" })
      .getByRole("radio", { name: "LLMで作る" }),
  ).toBeChecked();
});

test("while another session loads, the previous session's fields, history and generate bar are not shown", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  const state = await mockPromptExpanderApis(page);
  state.sessions.push(
    sessionPayload({
      id: "pe-session-2",
      title: "もうひとつのセッション",
      entry_count: 0,
      thumbnail_url: null,
    }),
  );
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  // 2 つ目のセッションの読み込みだけを止めておく
  await page.route(
    (url) => url.pathname === "/api/prompt-expander/sessions/pe-session-2",
    async (route) => {
      if (route.request().method() !== "GET") {
        await route.fallback();
        return;
      }
      await gate;
      await route.fallback();
    },
  );
  await openSession(page);
  await positiveField(page).fill("1girl, first session");
  // 画面を読み込み直さずに、一覧から別のセッションを開く
  await page.getByRole("button", { name: "← 一覧へ戻る" }).click();
  await page
    .getByRole("button", { name: "もうひとつのセッション を開く" })
    .click();
  await expect(page).toHaveURL(/\/prompt-expander\/pe-session-2$/);

  // 読み込み中は、前のセッションの欄・生成履歴・生成バーを出さない
  await expect(
    page.locator(".prompt-expander__workspace-composer"),
  ).toContainText("読み込み中…");
  await expect(
    page.locator(".prompt-expander__workspace-entries"),
  ).toContainText("読み込み中…");
  await expect(positiveField(page)).toHaveCount(0);
  await expect(generateButton(page)).toHaveCount(0);
  await expect(page.locator("[data-entry-id]")).toHaveCount(0);
  await page.keyboard.press("Control+Shift+Enter");

  release();
  await expect(positiveField(page)).toBeVisible();
  await expect(positiveField(page)).toHaveValue("");
  await expect(generateButton(page)).toBeVisible();
  expect(state.generateBodies).toHaveLength(0);
});

test("a rename that fails keeps the typed name so it can be saved again", async ({
  page,
}) => {
  await enableFeatures(page, { experimentalPromptExpanderEnabled: true });
  await mockPromptExpanderApis(page);
  let failRename = true;
  await page.route(
    (url) => url.pathname === `/api/prompt-expander/sessions/${SESSION_ID}`,
    async (route) => {
      if (route.request().method() === "PATCH" && failRename) {
        await route.fulfill({
          status: 503,
          json: { detail: { code: "unavailable", message: "unavailable" } },
        });
        return;
      }
      await route.fallback();
    },
  );
  await openSession(page);
  const header = page.locator(".prompt-expander__header");
  await header.getByRole("button", { name: "名前変更" }).click();
  const input = header.getByLabel("セッション名");
  await input.fill("改名したセッション");
  await input.press("Enter");
  // 失敗しても閉じず、入力した名前が残る
  await expect(input).toHaveValue("改名したセッション");
  await expect(input).toBeFocused();
  await expect(header).not.toContainText("改名したセッション", {
    useInnerText: true,
  });

  failRename = false;
  await input.press("Enter");
  await expect(header.getByLabel("セッション名")).toHaveCount(0);
  await expect(header).toContainText("改名したセッション");
});
