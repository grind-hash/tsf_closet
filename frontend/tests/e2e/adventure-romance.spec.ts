import { fileURLToPath } from "node:url";
import { expect, type Page, test } from "@playwright/test";

const IMAGE = "/mock-scene.png";
const IMAGE_PATH = fileURLToPath(
  new URL("../../../backend/images/characters/char1_v2.png", import.meta.url),
);
// AdventureScreen.tsx の主人公セレクト特殊値と揃える
const ROMANCE_PLAYER_SESSION_VALUE = "__session__";

function simPayload(overrides: Record<string, unknown> = {}) {
  return {
    total_days: 7,
    day: 1,
    slot: "day",
    affection: 10,
    stage: "stranger",
    money: 5000,
    partner_name: "美咲",
    player_name: "水瀬ユウヤ",
    player_character_id: "char1",
    job: { name: "カフェ", wage: 3000 },
    gift_catalog: [
      { id: "g1", name: "花束", price: 1500, tier: "budget" },
      { id: "g2", name: "ネックレス", price: 12000, tier: "luxury" },
    ],
    given_gift_ids: [],
    confession_available: false,
    ...overrides,
  };
}

function romanceRunPayload(
  turnCount = 0,
  overrides: Record<string, unknown> = {},
) {
  return {
    id: "run-1",
    source_session_id: "session-1",
    source_history_id: null,
    scenario_template_id: null,
    preset: "romance",
    title: "恋愛シミュレーション",
    objective: "7日以内に美咲と想いを通わせ、交際を始める",
    setting: "学園近くの商店街",
    constraints: ["美咲は放課後しか会えない"],
    status: "active",
    turn_count: turnCount,
    max_turns: 14,
    remaining_turns: 14 - turnCount,
    ending_title: null,
    ending_summary: null,
    clues: [],
    reality_rules: [],
    milestones: [
      { id: "become_friends", label: "友人になる" },
      { id: "mutual_interest", label: "意識し合う" },
      { id: "mutual_love", label: "両想いになる" },
      { id: "start_dating", label: "交際を始める" },
    ],
    completed_milestones: [],
    opening_narrative: "商店街の書店で美咲と目が合った。",
    choices: [
      { id: "a", label: "美咲に話しかける" },
      { id: "b", label: "本棚を眺める" },
      { id: "c", label: "店を出る" },
    ],
    current_image_url: IMAGE,
    current_image_prompt: null,
    use_precise_reference: false,
    enable_composite_scene: false,
    respect_clothing_layers: false,
    narration_voice: "second_person",
    narration_pronoun: "僕",
    opening_image_url: IMAGE,
    background_image_url: IMAGE,
    portrait_image_url: IMAGE,
    opening_portrait_url: IMAGE,
    partner_portrait_url: "/mock-partner.png",
    opening_partner_portrait_url: "/mock-partner.png",
    visual_state: {
      location: "商店街の書店",
      appearance: "制服姿の主人公",
      clothing: "学園の制服",
      surroundings: "夕暮れの書店",
      main_characters: [],
    },
    sim: simPayload(),
    opening_sim: simPayload(),
    turns: [],
    created_at: "2026-08-01T00:00:00",
    updated_at: "2026-08-01T00:00:00",
    ...overrides,
  };
}

async function enableAdventure(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
    window.localStorage.setItem(
      "app_settings",
      JSON.stringify({ experimentalAdventureEnabled: true }),
    );
  });
}

interface RomanceMockState {
  streamBodies: Record<string, unknown>[];
  createBodies: Record<string, unknown>[];
  runAfterTurn: Record<string, unknown> | null;
}

async function mockRomanceApis(
  page: Page,
  initialRun: Record<string, unknown> = romanceRunPayload(),
): Promise<RomanceMockState> {
  const state: RomanceMockState = {
    streamBodies: [],
    createBodies: [],
    runAfterTurn: null,
  };
  let turnTaken = false;
  await page.route("**/api/mock-scene.png", async (route) => {
    await route.fulfill({ path: IMAGE_PATH, contentType: "image/png" });
  });
  await page.route("**/api/mock-partner.png", async (route) => {
    await route.fulfill({ path: IMAGE_PATH, contentType: "image/png" });
  });
  await page.route("**/api/mock-partner-turn.png", async (route) => {
    await route.fulfill({ path: IMAGE_PATH, contentType: "image/png" });
  });
  await page.route("**/api/gallery/sessions?*", async (route) => {
    await route.fulfill({
      json: {
        sessions: [
          {
            session_id: "session-1",
            character_name: "テストキャラクター",
            thumbnail_url: IMAGE,
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
      json: {
        items: [
          {
            id: "h1",
            session_id: "session-1",
            image_url: IMAGE,
            instruction: "猫耳メイドに変身",
            timestamp: "2026-08-01T00:00:00",
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        has_more: false,
      },
    });
  });
  await page.route("**/api/adventure/templates", async (route) => {
    await route.fulfill({ json: { templates: [] } });
  });
  await page.route("**/api/game/characters", async (route) => {
    await route.fulfill({
      json: {
        characters: [
          {
            id: "char1",
            name: "水瀬ユウヤ",
            thumbnail: "",
            description: "普通の男の子。",
          },
          {
            id: "char2",
            name: "星野エミ",
            thumbnail: "",
            description: "普通の女の子。",
          },
        ],
      },
    });
  });
  await page.route("**/api/adventure/setup/generate", async (route) => {
    const request = route.request().postDataJSON() as {
      preset: string;
      scenario_max_turns: number;
    };
    expect(request.preset).toBe("romance");
    // 既定7日 → 日数×2 = 14ターン
    expect(request.scenario_max_turns).toBe(14);
    await route.fulfill({
      json: {
        setting: "学園近くの商店街",
        objective: "7日以内に美咲と想いを通わせ、交際を始める",
        constraints: ["美咲は放課後しか会えない"],
      },
    });
  });
  await page.route("**/api/adventure/runs", async (route) => {
    if (route.request().method() === "POST") {
      // 送信ボディはテスト側で検証する
      state.createBodies.push(
        route.request().postDataJSON() as Record<string, unknown>,
      );
      await route.fulfill({ status: 201, json: initialRun });
    } else {
      await route.fulfill({ json: { runs: [] } });
    }
  });
  await page.route("**/api/adventure/runs/run-1", async (route) => {
    await route.fulfill({
      json: turnTaken && state.runAfterTurn ? state.runAfterTurn : initialRun,
    });
  });
  await page.route(
    "**/api/adventure/runs/run-1/turns/stream",
    async (route) => {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      state.streamBodies.push(body);
      turnTaken = true;
      const turn = {
        id: "turn-1",
        turn_number: 1,
        client_turn_id: String(body.client_turn_id ?? "client-1"),
        user_input: String(body.user_input ?? ""),
        input_kind: String(body.input_kind ?? "free_text"),
        narrative: "ふたりの距離が少し縮まった。",
        location: "商店街の書店",
        choices: (initialRun as { choices: unknown[] }).choices,
        image_url: null,
        image_status: "not_requested",
        portrait_image_url: IMAGE,
        portrait_status: "completed",
        created_at: "2026-08-01T00:10:00",
        run_status: "active",
        remaining_turns: 13,
        clues: ["静かな時間の過ごし方に関心がある。"],
        completed_milestones: [],
        sim: simPayload({ day: 1, slot: "night", affection: 13 }),
      };
      await route.fulfill({
        contentType: "text/event-stream",
        body: `event: status\ndata: {"phase":"narrative"}\n\nevent: narrative_done\ndata: {"narrative":"ふたりの距離が少し縮まった。"}\n\nevent: turn\ndata: ${JSON.stringify(turn)}\n\nevent: complete\ndata: {"status":"active"}\n\n`,
      });
    },
  );
  return state;
}

test("start a romance run with day select and show the romance HUD", async ({
  page,
}) => {
  await enableAdventure(page);
  const state = await mockRomanceApis(page);
  await page.goto("/adventure");

  await page.getByRole("button", { name: /^恋愛シミュレーション/ }).click();
  // ターン数入力の代わりに日数セレクト（既定7日）が出る
  const daySelect = page.getByLabel(/日数/);
  await expect(daySelect).toHaveValue("7");
  // 主人公(自分)セレクト。既定は男性キャラ char1
  const playerSelect = page.getByLabel(/主人公（自分）/);
  await expect(playerSelect).toHaveValue("char1");
  await expect(playerSelect.locator("option").first()).toHaveText("水瀬ユウヤ");
  await page.getByRole("button", { name: "ミッション案を自動生成" }).click();
  await expect(page.getByLabel("ゴール")).toHaveValue(
    "7日以内に美咲と想いを通わせ、交際を始める",
  );
  await page.getByRole("button", { name: "シナリオを開始" }).click();

  await expect(page).toHaveURL(/\/adventure\/run-1$/);
  // 主人公(自分)は既定でテンプレキャラ char1 を送る
  expect(state.createBodies[0]).toMatchObject({
    preset: "romance",
    scenario_max_turns: 14,
    romance_player_character_id: "char1",
  });
  // romance HUD: Day/時間帯・好感度・所持金
  await expect(page.getByText("Day 1/7")).toBeVisible();
  await expect(page.getByText("好感度")).toBeVisible();
  await expect(page.getByText("所持金")).toBeVisible();
  await expect(page.getByText("5,000")).toBeVisible();
  // 手掛かりチップは「ヒント」に差し替わる
  await expect(page.getByRole("button", { name: /^ヒント/ })).toBeVisible();
  // 非合成モードでは攻略対象の立ち絵も並置表示される
  await expect(page.getByAltText("攻略対象の立ち絵")).toBeVisible();
  // 行動ボタン行。告白は好感度不足のため出ない
  await expect(page.getByRole("button", { name: "バイトする" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "プレゼントを贈る" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "属性を付与" })).toBeVisible();
  await expect(page.getByRole("button", { name: "想いを告げる" })).toBeHidden();
});

test("show heroine info in the romance turn detail modal", async ({ page }) => {
  await enableAdventure(page);
  const runWithTurn = romanceRunPayload(2, {
    // 最新の攻略対象立ち絵はターン2で更新された1枚
    partner_portrait_url: "/mock-partner-turn.png",
    turns: [
      {
        id: "turn-1",
        turn_number: 2,
        client_turn_id: "c1",
        user_input: "特製ドリンクを渡す",
        input_kind: "choice",
        narrative: "彼女は嬉しそうに受け取った。",
        location: "商店街の書店",
        choices: [
          { id: "a", label: "感想を聞く" },
          { id: "b", label: "隣に座る" },
          { id: "c", label: "店を出る" },
        ],
        image_url: null,
        image_status: "not_requested",
        portrait_image_url: IMAGE,
        portrait_status: "completed",
        created_at: "2026-08-01T00:10:00",
        // ターン確定時点の公開シミュ状態（run GET の turns に載る）
        sim: simPayload({ day: 2, slot: "day", affection: 13 }),
        partner_note: "グラスを受け取り、口元に微笑みを浮かべている",
        partner_portrait_url: "/mock-partner-turn.png",
      },
    ],
  });
  await mockRomanceApis(page, runWithTurn);
  await page.goto("/adventure/run-1");

  await page.locator(".adventure-stage__image-button").click();

  // モーダルは romance テーマでスコープされる
  const modal = page.locator(".image-preview-modal__overlay");
  await expect(modal).toHaveClass(/adventure-preview--romance/);
  // 攻略対象カード: 名前・好感度・関係段階・その時の様子
  await expect(modal.getByRole("heading", { name: "攻略対象" })).toBeVisible();
  await expect(modal.getByText("美咲", { exact: true })).toBeVisible();
  await expect(modal.getByText("13/100")).toBeVisible();
  await expect(modal.getByText("知り合い", { exact: true })).toBeVisible();
  await expect(
    modal.getByText("グラスを受け取り、口元に微笑みを浮かべている"),
  ).toBeVisible();
  // 手番は Day 表記になる: 手番2 = Day1 夜
  await expect(modal.getByText("Day 1/7 夜（2/14手）")).toBeVisible();

  // 切替チップから、この手番時点の相手の立ち絵ビューへ移動できる
  const partnerChip = modal.getByRole("button", { name: "攻略対象" });
  await expect(partnerChip).toBeVisible();
  await partnerChip.click();
  await expect(modal.locator(".image-preview-modal__image")).toHaveAttribute(
    "src",
    /mock-partner-turn\.png/,
  );

  // 開幕フレームでも開始時点(好感度10)のカードと開幕時の立ち絵を表示する
  await page.locator(".image-preview-modal__nav--prev").click();
  await expect(modal.getByText("開始", { exact: true })).toBeVisible();
  await expect(modal.getByText("美咲", { exact: true })).toBeVisible();
  await expect(modal.getByText("10/100")).toBeVisible();
  await expect(partnerChip).toBeVisible();
  await partnerChip.click();
  await expect(modal.locator(".image-preview-modal__image")).toHaveAttribute(
    "src",
    /mock-partner\.png/,
  );

  // ステージでも過去フレーム選択中に攻略対象の立ち絵が消えない
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "ログ" }).click();
  await page.getByAltText("手番 0 の場面").click();
  await expect(page.getByText("過去の場面を表示中")).toBeVisible();
  await expect(page.getByAltText("攻略対象の立ち絵")).toBeVisible();
});

test("player can be a transformed state from a session", async ({ page }) => {
  await enableAdventure(page);
  const state = await mockRomanceApis(page);
  await page.goto("/adventure");

  await page.getByRole("button", { name: /^恋愛シミュレーション/ }).click();
  await page
    .getByLabel(/主人公（自分）/)
    .selectOption(ROMANCE_PLAYER_SESSION_VALUE);
  // 主人公セッションと時点ピッカーが現れ、変身時点を選べる
  const playerSource = page.locator(".adventure-romance-player-source");
  await expect(playerSource.getByLabel(/主人公にするセッション/)).toHaveValue(
    "session-1",
  );
  await playerSource.getByRole("button", { name: "猫耳メイドに変身" }).click();
  await page.getByRole("button", { name: "ミッション案を自動生成" }).click();
  await page.getByRole("button", { name: "シナリオを開始" }).click();

  await expect(page).toHaveURL(/\/adventure\/run-1$/);
  expect(state.createBodies[0]).toMatchObject({
    romance_player_session_id: "session-1",
    romance_player_history_id: "h1",
  });
  expect(state.createBodies[0]).not.toHaveProperty(
    "romance_player_character_id",
  );
});

test("gift shop purchase sends input_kind gift with gift_id", async ({
  page,
}) => {
  await enableAdventure(page);
  const state = await mockRomanceApis(page);
  await page.goto("/adventure/run-1");

  await page.getByRole("button", { name: "プレゼントを贈る" }).click();
  const modal = page.getByRole("dialog", { name: "ギフトショップ" });
  await expect(modal.getByText("花束")).toBeVisible();
  // 所持金5,000ではネックレス(12,000)は買えない
  const rows = modal.locator(".adventure-gift-shop__list li");
  await expect(
    rows.filter({ hasText: "ネックレス" }).getByRole("button", {
      name: "贈る",
    }),
  ).toBeDisabled();
  await rows
    .filter({ hasText: "花束" })
    .getByRole("button", { name: "贈る" })
    .click();

  await expect(page.getByText("ふたりの距離が少し縮まった。")).toBeVisible();
  expect(state.streamBodies).toHaveLength(1);
  expect(state.streamBodies[0]).toMatchObject({
    input_kind: "gift",
    gift_id: "g1",
    user_input: "花束を購入して贈る",
  });
});

test("attribute modal sends a reality declaration and lists it in the HUD", async ({
  page,
}) => {
  await enableAdventure(page);
  const state = await mockRomanceApis(page);
  state.runAfterTurn = romanceRunPayload(1, {
    reality_rules: ["彼女は猫耳が生えている"],
    sim: simPayload({ day: 1, slot: "night" }),
  });
  await page.goto("/adventure/run-1");

  await page.getByRole("button", { name: "属性を付与" }).click();
  const modal = page.getByRole("dialog", { name: "属性を付与" });
  await modal.getByLabel("付与する属性").fill("彼女は猫耳が生えている");
  await modal.getByRole("button", { name: "付与する" }).click();

  await expect(page.getByText("ふたりの距離が少し縮まった。")).toBeVisible();
  expect(state.streamBodies[0]).toMatchObject({
    input_kind: "reality_alter",
    user_input: "現実改変：彼女は猫耳が生えている",
  });
  // ストリーム後の run 再取得で「付与した属性」チップが出る
  const attributeChip = page.getByRole("button", { name: /^付与した属性/ });
  await expect(attributeChip).toBeVisible();
  await attributeChip.click();
  await expect(page.getByText("彼女は猫耳が生えている")).toBeVisible();
});

test("confession button appears when available and sends input_kind confess", async ({
  page,
}) => {
  await enableAdventure(page);
  const state = await mockRomanceApis(
    page,
    romanceRunPayload(6, {
      sim: simPayload({
        day: 4,
        slot: "day",
        affection: 80,
        stage: "mutual",
        confession_available: true,
      }),
    }),
  );
  await page.goto("/adventure/run-1");

  const confess = page.getByRole("button", { name: "想いを告げる" });
  await expect(confess).toBeVisible();
  await confess.click();
  await expect(page.getByText("ふたりの距離が少し縮まった。")).toBeVisible();
  expect(state.streamBodies[0]).toMatchObject({
    input_kind: "confess",
    user_input: "美咲に想いを告げる",
  });
});
