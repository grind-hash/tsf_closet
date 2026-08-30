import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
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
    partner_speech_style: "丁寧語。一人称はわたし",
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
    player_speech_style: "polite",
    player_speech_custom: "",
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

// Anlas確認ダイアログはNovelAI画像プロバイダーのときだけ出るため、
// /health をモックしてプロバイダーを固定する
async function mockNovelaiHealth(page: Page) {
  await page.route("**/health", async (route) => {
    await route.fulfill({
      json: {
        status: "ok",
        services: {},
        image_provider: "novelai",
        image_description_provider: "novelai",
        feeling_provider: "novelai",
      },
    });
  });
}

// 実DBのユーザー設定(V5選択中など)に依存しないよう、画像モデルをV4.5に固定する。
// V5実効時は精密参照が無効になりAnlas確認ダイアログも出ないため、
// 精密参照系のテストはこのモックを併用する
async function mockV45ImageModels(page: Page) {
  await page.route("**/api/settings/user", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    const response = await route.fetch();
    const json = await response.json();
    json.novelai_image_model = "nai-diffusion-4-5-full";
    json.novelai_curated_image_model = "nai-diffusion-4-5-curated";
    await route.fulfill({ response, json });
  });
}

interface RomanceMockState {
  streamBodies: Record<string, unknown>[];
  createBodies: Record<string, unknown>[];
  runAfterTurn: Record<string, unknown> | null;
  /** PATCH /reality-rules のボディ。手番を消費しない付与・編集・削除の記録 */
  realityRuleBodies: { rules: string[] }[];
  /** PATCH /settings のボディ。口調変更も手番を消費しない */
  settingsBodies: Record<string, unknown>[];
}

async function mockRomanceApis(
  page: Page,
  initialRun: Record<string, unknown> = romanceRunPayload(),
): Promise<RomanceMockState> {
  const state: RomanceMockState = {
    streamBodies: [],
    createBodies: [],
    runAfterTurn: null,
    realityRuleBodies: [],
    settingsBodies: [],
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
  // runs/run-1 より後に登録する(Playwright はハンドラを後勝ちで解決する)
  await page.route(
    "**/api/adventure/runs/run-1/reality-rules",
    async (route) => {
      const body = route.request().postDataJSON() as { rules: string[] };
      state.realityRuleBodies.push(body);
      await route.fulfill({
        json: { ...initialRun, reality_rules: body.rules },
      });
    },
  );
  await page.route("**/api/adventure/runs/run-1/settings", async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    state.settingsBodies.push(body);
    await route.fulfill({
      json: {
        ...initialRun,
        player_speech_style: body.player_speech_style,
        player_speech_custom: body.player_speech_custom,
        sim: simPayload({
          partner_speech_style: body.partner_speech_style as string,
        }),
      },
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
  // 5〜30日を選べる（backend/gateway/consts/adventure_romance.py と揃える）
  await expect(daySelect.locator("option")).toHaveCount(26);
  await expect(daySelect.locator("option").first()).toHaveAttribute(
    "value",
    "5",
  );
  await expect(daySelect.locator("option").last()).toHaveAttribute(
    "value",
    "30",
  );
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
  // romance HUD: Day/時間帯・好感度・所持金(タイルはラベルと値が別要素)
  const dayTile = page.locator(".adventure-hud__day");
  await expect(dayTile).toContainText("Day");
  await expect(dayTile).toContainText("1/7");
  await expect(dayTile).toContainText("昼");
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

test("choose a speech style at setup and change it during play", async ({
  page,
}) => {
  await enableAdventure(page);
  const state = await mockRomanceApis(page);
  await page.goto("/adventure");

  await page.getByRole("button", { name: /^恋愛シミュレーション/ }).click();
  await page.getByRole("button", { name: "ミッション案を自動生成" }).click();
  await expect(page.getByLabel("ゴール")).toHaveValue(
    "7日以内に美咲と想いを通わせ、交際を始める",
  );

  // 物語の演出に主人公と攻略対象の口調が並んで置かれる
  await page.getByText("物語の演出").click();
  await page.getByRole("button", { name: /^ため口/ }).click();
  await page
    .getByLabel("攻略対象の口調")
    .fill("ため口。語尾を伸ばすギャル口調");

  await page.getByRole("button", { name: "シナリオを開始" }).click();
  await expect(page).toHaveURL(/\/adventure\/run-1$/);
  expect(state.createBodies[0]).toMatchObject({
    player_speech_style: "casual",
    romance_partner_speech_style: "ため口。語尾を伸ばすギャル口調",
  });

  // 口調は常時見えているHUDチップに出て、1クリックで主人公と攻略対象が対で並ぶ
  const speechChip = page.getByRole("button", { name: /^口調/ });
  await expect(speechChip).toContainText("丁寧語");
  await speechChip.click();
  const popover = page.getByRole("dialog", { name: "主人公の口調" });
  await expect(popover).toContainText("丁寧語");
  await expect(popover).toContainText("丁寧語。一人称はわたし");

  // プレイ中の変更は手番を消費せず PATCH で保存される
  await popover.getByRole("button", { name: "口調を変更" }).click();
  const modal = page.getByRole("dialog", { name: "口調を変更" });
  await modal.getByRole("button", { name: /^かしこまった敬語/ }).click();
  await modal.getByLabel("攻略対象の口調").fill("ため口で親しげに話す");
  await modal.getByRole("button", { name: "保存" }).click();

  await expect(modal).toBeHidden();
  expect(state.settingsBodies).toHaveLength(1);
  expect(state.settingsBodies[0]).toMatchObject({
    player_speech_style: "formal",
    partner_speech_style: "ため口で親しげに話す",
    // 画像設定は現在値のまま送り、意図せず切り替わらないこと
    use_precise_reference: false,
    enable_composite_scene: false,
  });
  // 手番は消費しない
  expect(state.streamBodies).toHaveLength(0);
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
        // ターン確定時点の公開シミュ状態（run GET の turns に載る）。
        // 手番2が描いている枠はサーバ導出の scene_day/scene_slot で伝わる
        sim: simPayload({
          day: 2,
          slot: "day",
          scene_day: 1,
          scene_slot: "night",
          affection: 13,
        }),
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
  // 過去閲覧中は行動UIの代わりに案内文が出て、選択肢は残らない
  await expect(
    page.getByText("行動するには最新の場面へ戻ってください"),
  ).toBeVisible();
  await expect(page.locator(".adventure-choices")).toHaveCount(0);
  await expect(page.locator(".adventure-romance-actions")).toHaveCount(0);
});

test("player can be a transformed state from a session", async ({ page }) => {
  await enableAdventure(page);
  const state = await mockRomanceApis(page);
  await page.goto("/adventure");

  await page.getByRole("button", { name: /^恋愛シミュレーション/ }).click();
  await page
    .getByLabel(/主人公（自分）/)
    .selectOption(ROMANCE_PLAYER_SESSION_VALUE);
  // 先頭セッションの「現在の状態」がサマリに自動選択される
  const playerSource = page.locator(".adventure-romance-player-source");
  await expect(playerSource.getByRole("group")).toContainText(
    "テストキャラクター",
  );
  // 選択モーダルを開き、セッション内の変身時点を選ぶ
  await playerSource.getByRole("button", { name: "変更" }).click();
  const picker = page.getByRole("dialog", { name: "主人公にするセッション" });
  await picker
    .getByRole("button", { name: "テストキャラクター の時点を選ぶ" })
    .click();
  await picker.getByRole("button", { name: "猫耳メイドに変身" }).click();
  await expect(picker).toBeHidden();
  await expect(playerSource.getByRole("group")).toContainText(
    "猫耳メイドに変身",
  );
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
  const modal = page.getByRole("dialog", { name: "属性を管理" });
  await modal.getByLabel("付与する属性").fill("彼女は猫耳が生えている");
  await modal.getByRole("button", { name: "付与して行動" }).click();

  await expect(page.getByText("ふたりの距離が少し縮まった。")).toBeVisible();
  expect(state.streamBodies[0]).toMatchObject({
    input_kind: "reality_alter",
    user_input: "現実改変：彼女は猫耳が生えている",
  });
  // 行動を伴う付与はターン側が追記するので PATCH は走らない
  expect(state.realityRuleBodies).toHaveLength(0);
  // ストリーム後の run 再取得で「付与した属性」チップが出る
  const attributeChip = page.getByRole("button", { name: /^付与した属性/ });
  await expect(attributeChip).toBeVisible();
  await attributeChip.click();
  await expect(page.getByText("彼女は猫耳が生えている")).toBeVisible();
});

test("attribute modal grants without consuming a turn", async ({ page }) => {
  await enableAdventure(page);
  const state = await mockRomanceApis(page);
  await page.goto("/adventure/run-1");

  await page.getByRole("button", { name: "属性を付与" }).click();
  const modal = page.getByRole("dialog", { name: "属性を管理" });
  await modal.getByLabel("付与する属性").fill("彼女は猫耳が生えている");
  await modal.getByRole("button", { name: "付与のみ" }).click();

  await expect.poll(() => state.realityRuleBodies.length).toBeGreaterThan(0);
  expect(state.realityRuleBodies[0]).toEqual({
    rules: ["彼女は猫耳が生えている"],
  });
  // 手番を消費しないことがこの機能の要点
  expect(state.streamBodies).toHaveLength(0);
  // モーダルは開いたままで、一覧へ反映される(続けて付与できる)。
  // ヒント文にも同じ例文が入るため exact 指定で一覧の行だけを見る
  await expect(
    modal.getByText("彼女は猫耳が生えている", { exact: true }),
  ).toBeVisible();
});

test("attribute modal edits and deletes granted attributes", async ({
  page,
}) => {
  await enableAdventure(page);
  const state = await mockRomanceApis(
    page,
    romanceRunPayload(1, {
      reality_rules: ["彼女は猫耳が生えている", "彼女は語尾ににゃを付ける"],
    }),
  );
  await page.goto("/adventure/run-1");

  await page.getByRole("button", { name: /^付与した属性/ }).click();
  await page.getByRole("button", { name: "属性を管理" }).click();
  const modal = page.getByRole("dialog", { name: "属性を管理" });

  await modal
    .getByRole("button", { name: "「彼女は猫耳が生えている」を編集" })
    .click();
  const field = modal.getByLabel("内容を編集");
  await expect(field).toHaveValue("彼女は猫耳が生えている");
  await field.fill("彼女は狐耳が生えている");
  await modal.getByRole("button", { name: "保存" }).click();

  await expect.poll(() => state.realityRuleBodies.length).toBe(1);
  expect(state.realityRuleBodies[0]).toEqual({
    rules: ["彼女は狐耳が生えている", "彼女は語尾ににゃを付ける"],
  });

  await modal
    .getByRole("button", { name: "「彼女は語尾ににゃを付ける」を削除" })
    .click();
  await expect.poll(() => state.realityRuleBodies.length).toBe(2);
  expect(state.realityRuleBodies[1]).toEqual({
    rules: ["彼女は狐耳が生えている"],
  });

  // 一覧の操作はいずれも手番を消費しない
  expect(state.streamBodies).toHaveLength(0);
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

test("precise reference shows an Anlas confirmation before submitting a turn", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockNovelaiHealth(page);
  await mockV45ImageModels(page);
  const state = await mockRomanceApis(
    page,
    romanceRunPayload(0, { use_precise_reference: true }),
  );
  await page.route("**/api/game/anlas", async (route) => {
    await route.fulfill({
      json: { fixed_anlas: 100, purchased_anlas: 0, total_anlas: 100 },
    });
  });
  await page.goto("/adventure/run-1");

  // 選択肢クリックでは送信されず、確認ダイアログが出る
  await page.getByRole("button", { name: /美咲に話しかける/ }).click();
  await expect(page.getByText("Anlas 追加消費の確認")).toBeVisible();
  // 合成OFFのromanceターンは立ち絵2枚(参照2枚)で見積もり10 Anlas
  await expect(page.getByText("見積もり: 10 Anlas")).toBeVisible();
  expect(state.streamBodies).toHaveLength(0);

  // キャンセルで閉じ、送信もされない
  await page.getByRole("button", { name: "キャンセル" }).click();
  await expect(page.getByText("Anlas 追加消費の確認")).not.toBeVisible();
  expect(state.streamBodies).toHaveLength(0);

  // 抑止チェック付きで続行すると送信される
  await page.getByRole("button", { name: /美咲に話しかける/ }).click();
  await page.getByLabel("ブラウザを閉じるまで表示しない").check();
  await page.getByRole("button", { name: "続行" }).click();
  await expect(page.getByText("ふたりの距離が少し縮まった。")).toBeVisible();
  expect(state.streamBodies).toHaveLength(1);

  // 抑止後はダイアログを出さず直接送信する
  await page.getByRole("button", { name: /美咲に話しかける/ }).click();
  await expect.poll(() => state.streamBodies.length).toBe(2);
  await expect(page.getByText("Anlas 追加消費の確認")).not.toBeVisible();
});

test("precise reference shows an Anlas confirmation before starting a run", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockNovelaiHealth(page);
  await mockV45ImageModels(page);
  const state = await mockRomanceApis(page);
  await page.goto("/adventure");

  await page.getByRole("button", { name: /^恋愛シミュレーション/ }).click();
  await page.getByRole("button", { name: "ミッション案を自動生成" }).click();
  await expect(page.getByLabel("ゴール")).toHaveValue(
    "7日以内に美咲と想いを通わせ、交際を始める",
  );
  // 精密参照トグルは折りたたみ内。トグルスイッチ化で素のcheckboxは
  // 非表示のため、セクションを開いてからラベルをクリックして切り替える
  await page.getByText("生成オプション", { exact: true }).click();
  await page
    .locator("label.adventure-precise-toggle", {
      hasText: "精密参照画像を使う",
    })
    .click();
  await expect(page.getByLabel(/精密参照画像を使う/)).toBeChecked();
  await page
    .locator("label.adventure-precise-toggle", {
      hasText: "背景と人物を同時に描く",
    })
    .click();
  await expect(page.getByLabel(/背景と人物を同時に描く/)).toBeChecked();

  // 開始クリックでは run を作らず、確認ダイアログが出る
  await page.getByRole("button", { name: "シナリオを開始" }).click();
  await expect(page.getByText("Anlas 追加消費の確認")).toBeVisible();
  // 合成ONのromance開始は立ち絵2枚+合成シーン1〜2枚で見積もり15〜20 Anlas
  await expect(page.getByText("見積もり: 15〜20 Anlas")).toBeVisible();
  expect(state.createBodies).toHaveLength(0);

  // キャンセルで閉じ、作成もされない
  await page.getByRole("button", { name: "キャンセル" }).click();
  await expect(page.getByText("Anlas 追加消費の確認")).not.toBeVisible();
  expect(state.createBodies).toHaveLength(0);

  // 続行すると run が作成されプレイ画面へ遷移する
  await page.getByRole("button", { name: "シナリオを開始" }).click();
  await page.getByRole("button", { name: "続行" }).click();
  await expect(page).toHaveURL(/\/adventure\/run-1$/);
  expect(state.createBodies).toHaveLength(1);
  expect(state.createBodies[0]).toMatchObject({
    use_precise_reference: true,
  });
});

test("a played romance run can be selected and replayed", async ({ page }) => {
  await enableAdventure(page);
  const saved = romanceRunPayload(14, {
    id: "saved-romance-1",
    title: "以前の恋愛シミュレーション",
    status: "success",
    turn_count: 14,
    remaining_turns: 0,
  });
  const state = await mockRomanceApis(page);
  // 一覧に済み romance run を載せ、POST は通常どおり記録する
  await page.route("**/api/adventure/runs", async (route) => {
    if (route.request().method() === "POST") {
      state.createBodies.push(
        route.request().postDataJSON() as Record<string, unknown>,
      );
      await route.fulfill({ status: 201, json: romanceRunPayload() });
    } else {
      await route.fulfill({ json: { runs: [saved] } });
    }
  });
  await page.goto("/adventure");

  // 開始方式「シナリオを選ぶ」からピッカーを開くと romance も候補に並ぶ
  await page.getByRole("button", { name: "シナリオを選ぶ" }).click();
  const dialog = page.getByRole("dialog", { name: "シナリオを選ぶ" });
  await dialog.getByRole("tab", { name: "プレイしたシナリオ" }).click();
  await dialog
    .getByRole("button", { name: /以前の恋愛シミュレーション/ })
    .click();

  await expect(
    page
      .locator(".adventure-selected-scenario")
      .getByText("以前の恋愛シミュレーション", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "シナリオを開始" }).click();

  await expect(page).toHaveURL(/\/adventure\/run-1$/);
  expect(state.createBodies[0]).toMatchObject({
    preset: "romance",
    replay_run_id: "saved-romance-1",
  });
  // 主人公の選択はリクエストに載せず、サーバが元 run の sim から復元する
  expect(state.createBodies[0]).not.toHaveProperty(
    "romance_player_character_id",
  );
});

test("finished romance run offers replay from the result modal", async ({
  page,
}) => {
  await enableAdventure(page);
  const finished = romanceRunPayload(14, {
    status: "success",
    turn_count: 14,
    remaining_turns: 0,
    ending_title: "恋の成就",
    ending_summary: "ふたりは想いを重ね、恋人として歩き出した。",
    completed_milestones: [
      "become_friends",
      "mutual_interest",
      "mutual_love",
      "start_dating",
    ],
    choices: [],
  });
  await mockRomanceApis(page, finished);
  // ハブの一覧にも同じ run を載せ、リプレイ選択を解決できるようにする
  await page.route("**/api/adventure/runs", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ status: 201, json: romanceRunPayload() });
    } else {
      await route.fulfill({ json: { runs: [finished] } });
    }
  });
  await page.goto("/adventure/run-1");

  const result = page.getByRole("dialog", { name: "恋の成就" });
  await expect(result).toBeVisible();
  await result.getByRole("button", { name: "同じシナリオをもう一度" }).click();

  await expect(page).toHaveURL(/\/adventure$/);
  await expect(
    page
      .locator(".adventure-selected-scenario")
      .getByText("恋愛シミュレーション", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".adventure-selected-scenario")).toContainText(
    "プレイしたシナリオ",
  );
});

test("scenario overview is available from the preview modal", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockRomanceApis(page);
  await page.goto("/adventure/run-1");

  // モーダルの切替チップ列の先頭に「概要」があり、詳細パネルがシナリオ定義に切り替わる
  await page.locator(".adventure-stage__image-button").click();
  const modal = page.locator(".image-preview-modal__overlay");
  const caption = modal.locator(".image-preview-modal__caption");
  await expect(caption).toContainText("物語");
  await expect(
    modal.locator(".adventure-preview__views button").first(),
  ).toHaveText("概要");
  await modal.getByRole("button", { name: "概要", exact: true }).click();
  await expect(caption).toContainText("舞台");
  await expect(caption).toContainText("学園近くの商店街");
  await expect(caption).toContainText("制約");
  await expect(caption).toContainText("美咲は放課後しか会えない");
  // romance は日数(期限)も出す
  await expect(caption).toContainText("日数");
  await expect(caption).toContainText("7日間");
  // タイトルとゴールはヘッダに常時表示のまま、手番・物語とは入れ替わる
  await expect(caption).toContainText(
    "7日以内に美咲と想いを通わせ、交際を始める",
  );
  await expect(caption).not.toContainText("物語");

  // 閉じて開き直してもタブ選択は復元され、選択中のチップへフォーカスが当たる
  await page.keyboard.press("Escape");
  await page.locator(".adventure-stage__image-button").click();
  const overviewChip = modal.getByRole("button", {
    name: "概要",
    exact: true,
  });
  await expect(overviewChip).toHaveAttribute("aria-pressed", "true");
  await expect(overviewChip).toBeFocused();
  await expect(caption).toContainText("舞台");

  // シーンへ戻すと通常の詳細に戻る
  await modal.getByRole("button", { name: "シーン", exact: true }).click();
  await expect(caption).toContainText("物語");
  await expect(caption).not.toContainText("舞台");
});

test("choices and romance actions hide while a turn is streaming", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockRomanceApis(page);
  let releaseTurn: (() => void) | undefined;
  let turnDone = false;
  const turnTemplate = {
    id: "turn-1",
    turn_number: 1,
    client_turn_id: "client-1",
    user_input: "美咲に話しかける",
    input_kind: "choice",
    narrative: "ふたりの距離が少し縮まった。",
    location: "商店街の書店",
    choices: romanceRunPayload().choices,
    image_url: null,
    image_status: "not_requested",
    portrait_image_url: IMAGE,
    portrait_status: "completed",
    created_at: "2026-08-01T00:10:00",
    run_status: "active",
    remaining_turns: 13,
    clues: [],
    completed_milestones: [],
    sim: simPayload({ slot: "night", affection: 13 }),
  };
  // ストリーム完了後の run 全再取得でターンが載っているようにする
  await page.route("**/api/adventure/runs/run-1", async (route) => {
    await route.fulfill({
      json: turnDone
        ? romanceRunPayload(1, { turns: [turnTemplate] })
        : romanceRunPayload(),
    });
  });
  await page.route(
    "**/api/adventure/runs/run-1/turns/stream",
    async (route) => {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      await new Promise<void>((resolve) => {
        releaseTurn = resolve;
      });
      turnDone = true;
      // client_turn_id は FE の識別に使われるため、リクエストの値を返す
      const heldTurn = {
        ...turnTemplate,
        client_turn_id: String(body.client_turn_id ?? "client-1"),
        user_input: String(body.user_input ?? ""),
        input_kind: String(body.input_kind ?? "choice"),
      };
      await route.fulfill({
        contentType: "text/event-stream",
        body: `event: status\ndata: {"phase":"narrative"}\n\nevent: narrative_done\ndata: {"narrative":"ふたりの距離が少し縮まった。"}\n\nevent: turn\ndata: ${JSON.stringify(heldTurn)}\n\nevent: complete\ndata: {"status":"active"}\n\n`,
      });
    },
  );
  await page.goto("/adventure/run-1");

  await expect(page.locator(".adventure-choices")).toBeVisible();
  await page.getByRole("button", { name: /美咲に話しかける/ }).click();
  // 生成中は前ターンの選択肢と行動ボタンを無効表示で残さず、丸ごと隠す
  await expect(page.locator(".adventure-choices")).toHaveCount(0);
  await expect(page.locator(".adventure-romance-actions")).toHaveCount(0);
  // 自由入力欄は残す(フォーカス維持のため)
  await expect(page.locator(".adventure-freeinput__field")).toBeVisible();

  await expect.poll(() => Boolean(releaseTurn)).toBe(true);
  releaseTurn?.();
  await expect(page.getByText("ふたりの距離が少し縮まった。")).toBeVisible();
  await expect(page.locator(".adventure-choices")).toBeVisible();
  await expect(page.locator(".adventure-romance-actions")).toBeVisible();
});

test("partner tab stays available in composite mode", async ({ page }) => {
  await enableAdventure(page);
  await mockRomanceApis(
    page,
    romanceRunPayload(1, {
      enable_composite_scene: true,
      turns: [
        {
          id: "turn-1",
          turn_number: 1,
          client_turn_id: "c1",
          user_input: "美咲に話しかける",
          input_kind: "choice",
          narrative: "彼女は少し驚いた顔をした。",
          location: "商店街の書店",
          choices: [
            { id: "a", label: "感想を聞く" },
            { id: "b", label: "隣に座る" },
            { id: "c", label: "店を出る" },
          ],
          image_url: IMAGE,
          image_status: "completed",
          portrait_image_url: IMAGE,
          portrait_status: "completed",
          created_at: "2026-08-01T00:10:00",
          sim: simPayload({ slot: "night", affection: 13 }),
          partner_note: "本を抱えたまま、こちらを見つめている",
          // 合成モードでは攻略対象立ち絵をターン生成しないため URL は無い
          partner_portrait_url: null,
        },
      ],
    }),
  );
  await page.goto("/adventure/run-1");

  await page.locator(".adventure-stage__image-button").click();
  const modal = page.locator(".image-preview-modal__overlay");
  // 開幕の1枚を引き継いで攻略対象タブが使える
  const partnerChip = modal.getByRole("button", { name: "攻略対象" });
  await expect(partnerChip).toBeVisible();
  await partnerChip.click();
  await expect(modal.locator(".image-preview-modal__image")).toHaveAttribute(
    "src",
    /mock-partner\.png/,
  );
  // 前の手番(開幕)へ送ってもタブ選択は維持される
  await page.locator(".image-preview-modal__nav--prev").click();
  await expect(partnerChip).toHaveAttribute("aria-pressed", "true");
  await expect(modal.locator(".image-preview-modal__image")).toHaveAttribute(
    "src",
    /mock-partner\.png/,
  );
});

test("clue extraction is always on and has no toggle", async ({ page }) => {
  await enableAdventure(page);
  // 旧バージョンでOFFにしていたブラウザでも、以後は常にONへ倒す
  await page.addInitScript(() => {
    window.localStorage.setItem("adventure_generate_clues", "false");
  });
  const state = await mockRomanceApis(page);
  await page.goto("/adventure/run-1");

  await page.getByRole("button", { name: "画像生成設定" }).click();
  await expect(page.getByText("手掛かり・ヒントを抽出する")).toHaveCount(0);
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: /美咲に話しかける/ }).click();
  await expect(page.getByText("ふたりの距離が少し縮まった。")).toBeVisible();
  // 送らない = backend 既定の true
  expect(state.streamBodies[0]).not.toHaveProperty("generate_clues");
});

test("turn time estimate follows the image settings", async ({ page }) => {
  await enableAdventure(page);
  await mockRomanceApis(page);
  await page.route("**/api/adventure/runs/run-1/settings", async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ json: { ...romanceRunPayload(), ...body } });
  });
  await page.goto("/adventure/run-1");

  await page.getByRole("button", { name: "画像生成設定" }).click();
  // 既定(非合成・立ち絵2種ON)は 主人公18秒+攻略対象18秒+ベース20秒 → 約55秒
  await expect(page.getByText("1ターンの生成時間: 約55秒")).toBeVisible();
  // 合成ONは立ち絵2種の後に合成シーンを直列生成する → 約75秒
  await page
    .locator(
      ".adventure-image-settings-popover label.adventure-precise-toggle",
      { hasText: "背景と人物を同時に描く" },
    )
    .click();
  await expect(page.getByText("1ターンの生成時間: 約75秒")).toBeVisible();
  // 合成ON中も立ち絵トグルは操作でき、OFFにすると合成シーンだけの約40秒になる
  await page
    .locator(
      ".adventure-image-settings-popover label.adventure-precise-toggle",
      { hasText: "主人公の立ち絵を毎ターン描く" },
    )
    .click();
  await page
    .locator(
      ".adventure-image-settings-popover label.adventure-precise-toggle",
      { hasText: "攻略対象の立ち絵を毎ターン描く" },
    )
    .click();
  await expect(page.getByText("1ターンの生成時間: 約40秒")).toBeVisible();
});

test("image settings popover stays inside a short viewport", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockRomanceApis(page);
  // 縦が足りないディスプレイでも末尾のトグルが切れずに読めること
  await page.setViewportSize({ width: 1280, height: 520 });
  await page.goto("/adventure/run-1");

  await page.getByRole("button", { name: "画像生成設定" }).click();
  const popover = page.locator(".adventure-image-settings-popover");
  await expect(popover).toBeVisible();

  const fits = await popover.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return {
      bottomOverflow: rect.bottom - window.innerHeight,
      scrollable: element.scrollHeight > element.clientHeight,
    };
  });
  expect(fits.bottomOverflow).toBeLessThanOrEqual(0);
  // 収まりきらない分は枠内スクロールへ逃がす
  expect(fits.scrollable).toBe(true);

  // 先頭の生成時間は常に見えており、最後の項目までスクロールで到達できる
  await expect(popover.locator(".adventure-turn-estimate")).toBeInViewport();
  const lastToggle = popover
    .locator("label.adventure-precise-toggle")
    .filter({ hasText: "攻略対象の立ち絵を毎ターン描く" });
  await lastToggle.scrollIntoViewIfNeeded();
  await expect(lastToggle).toBeInViewport();
});

test("portrait toggles ride the turn request while the composite scene is on", async ({
  page,
}) => {
  await enableAdventure(page);
  await page.addInitScript(() => {
    window.localStorage.setItem("adventure_draw_portrait_every_turn", "false");
    window.localStorage.setItem("adventure_draw_partner_every_turn", "false");
  });
  const state = await mockRomanceApis(page, {
    ...romanceRunPayload(),
    enable_composite_scene: true,
  });
  await page.goto("/adventure/run-1");

  // 合成ONでも両トグルが表示され、OFF 状態を映す
  await page.getByRole("button", { name: "画像生成設定" }).click();
  await expect(
    page.getByLabel(/主人公の立ち絵を毎ターン描く/),
  ).not.toBeChecked();
  await expect(
    page.getByLabel(/攻略対象の立ち絵を毎ターン描く/),
  ).not.toBeChecked();
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: /美咲に話しかける/ }).click();
  await expect(page.getByText("ふたりの距離が少し縮まった。")).toBeVisible();
  expect(state.streamBodies[0]).toMatchObject({
    generate_portrait: false,
    generate_partner_portrait: false,
  });
});

test("image model override is chosen from the gear popover", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockV45ImageModels(page);
  const state = await mockRomanceApis(page);
  // 共有モックの settings 応答は上書きモデルを返さないため、ここだけ差し替える
  await page.route("**/api/adventure/runs/run-1/settings", async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    state.settingsBodies.push(body);
    await route.fulfill({
      json: romanceRunPayload(0, {
        image_model_override:
          body.image_model === "default" ? null : body.image_model,
      }),
    });
  });
  await page.goto("/adventure/run-1");

  await page.getByRole("button", { name: "画像生成設定" }).click();
  const picker = page.getByLabel("画像生成モデル");
  await expect(picker).toHaveValue("default");
  await picker.selectOption("nai-diffusion-5-full");

  // PATCH の応答が反映されるまで待つ(手番は消費しない)
  await expect(picker).toHaveValue("nai-diffusion-5-full");
  expect(state.settingsBodies).toHaveLength(1);
  expect(state.settingsBodies[0]).toMatchObject({
    image_model: "nai-diffusion-5-full",
    use_precise_reference: false,
    enable_composite_scene: false,
  });
  // V5 上書き中は精密参照が使えない
  await expect(page.getByLabel(/精密参照画像を使う/)).toBeDisabled();
  expect(state.streamBodies).toHaveLength(0);
});

// 設定画面の音声合成(TTS)が実DBで有効でもテスト結果が変わらないよう、
// ユーザー設定の GET を OFF に固定する
async function mockTtsDisabled(page: Page) {
  await page.route("**/api/settings/user", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    const response = await route.fetch();
    const json = await response.json();
    json.tts_enabled = false;
    await route.fulfill({ response, json });
  });
}

test("companion mode shows only the partner sprite and toggles from the gear popover", async ({
  page,
}) => {
  await enableAdventure(page);
  const state = await mockRomanceApis(page);
  const companionRun = romanceRunPayload(0, {
    companion_mode: true,
    opening_narrative:
      "美咲「こんにちは、また会えたね」\n夕日が書店に差し込む。",
  });
  await page.route("**/api/adventure/runs/run-1", async (route) => {
    await route.fulfill({ json: companionRun });
  });
  await page.route("**/api/adventure/runs/run-1/settings", async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    state.settingsBodies.push(body);
    await route.fulfill({
      json: romanceRunPayload(0, {
        companion_mode: body.companion_mode === true,
      }),
    });
  });
  await page.goto("/adventure/run-1");

  // 攻略対象の立ち絵だけを中央に置き、主人公の立ち絵は並置しない
  const partnerSprite = page.getByAltText("攻略対象の立ち絵");
  await expect(partnerSprite).toBeVisible();
  await expect(partnerSprite).toHaveClass(/adventure-stage__portrait--solo/);
  await expect(
    page.locator(".adventure-stage__frame .adventure-stage__portrait--paired"),
  ).toHaveCount(0);
  await expect(
    page.locator(".adventure-stage__frame img[alt='主人公のポートレート']"),
  ).toHaveCount(0);
  // 台本形式の行は話者ラベル付きで描かれる
  const speaker = page.locator(".adventure-messagebox__speaker").first();
  await expect(speaker).toHaveText("美咲");
  await expect(
    page.locator(".adventure-messagebox__line--dialogue").first(),
  ).toContainText("「こんにちは、また会えたね」");
  await expect(
    page.locator(".adventure-messagebox__line--narration").first(),
  ).toHaveText("夕日が書店に差し込む。");

  // ⚙のトグルは ON。OFF へ戻すと PATCH だけが飛び、手番は消費しない
  await page.getByRole("button", { name: "画像生成設定" }).click();
  // 合成シーン等のヒント文にも「対面会話モード」が含まれるため名前の先頭で絞る
  const toggle = page.getByRole("checkbox", { name: /^対面会話モード/ });
  await expect(toggle).toBeChecked();
  // 対面会話 中は無効になる設定を隠さず文言で説明する
  await expect(
    page.getByText(/対面会話モード中は合成シーンを描かないため/),
  ).toBeVisible();
  // input は視覚的に隠れるため、スイッチのラベルをクリックする
  await page
    .locator(".adventure-image-settings-popover .adventure-companion-toggle")
    .click();
  await expect(toggle).not.toBeChecked();
  expect(state.settingsBodies).toHaveLength(1);
  expect(state.settingsBodies[0]).toMatchObject({
    companion_mode: false,
    use_precise_reference: false,
    enable_composite_scene: false,
  });
  expect(state.streamBodies).toHaveLength(0);
});

test("talk mode chats with the partner without consuming a turn", async ({
  page,
}) => {
  await enableAdventure(page);
  const state = await mockRomanceApis(page);
  const talkBodies: Record<string, unknown>[] = [];
  await page.route("**/api/adventure/runs/run-1/talk/stream", async (route) => {
    talkBodies.push(route.request().postDataJSON() as Record<string, unknown>);
    const done = {
      user_entry: { id: "u1", role: "user", text: "やあ", after_turn: 0 },
      partner_entry: {
        id: "p1",
        role: "partner",
        text: "やっほー、来てくれたんだ",
        after_turn: 0,
      },
      turn_count: 0,
    };
    await route.fulfill({
      contentType: "text/event-stream",
      body: `event: status\ndata: {"phase":"talk"}\n\nevent: talk_chunk\ndata: {"chunk":"やっほー、"}\n\nevent: talk_chunk\ndata: {"chunk":"来てくれたんだ"}\n\nevent: talk_done\ndata: ${JSON.stringify(done)}\n\nevent: complete\ndata: {"status":"active"}\n\n`,
    });
  });
  await page.goto("/adventure/run-1");

  // 既定は行動モード。選択肢とバイトが出ている
  await expect(page.getByRole("button", { name: "バイト" })).toBeVisible();
  await page.getByRole("button", { name: "トーク" }).click();
  await expect(page.getByRole("button", { name: "バイト" })).toHaveCount(0);
  await expect(page.locator(".adventure-choices")).toHaveCount(0);
  await expect(page.getByText(/美咲に話しかけてみましょう/)).toBeVisible();

  const field = page.getByLabel("美咲に話しかける");
  await field.fill("やあ");
  await page.getByRole("button", { name: "送信" }).click();

  const thread = page.locator(".adventure-talk-thread");
  await expect(
    thread.locator(".adventure-talk-thread__entry--partner"),
  ).toContainText("やっほー、来てくれたんだ");
  await expect(
    thread.locator(".adventure-talk-thread__entry--user"),
  ).toContainText("やあ");
  expect(talkBodies).toEqual([{ user_input: "やあ" }]);
  // 手番は消費されず、Day 表示も変わらない
  expect(state.streamBodies).toHaveLength(0);
  await expect(page.locator(".adventure-hud__day")).toContainText("1");

  // 行動へ戻すと選択肢が復帰する
  await page.getByRole("button", { name: "行動", exact: true }).click();
  await expect(page.getByRole("button", { name: "バイト" })).toBeVisible();
});

test("sound popover shows the voice toggle disabled while TTS is off", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockTtsDisabled(page);
  await mockRomanceApis(page);
  await page.goto("/adventure/run-1");

  await page.getByRole("button", { name: "サウンド設定" }).click();
  // トグルスイッチの input は視覚的に隠れるため、文言の表示と disabled で確認する
  await expect(page.getByText("攻略対象のセリフを読み上げる")).toBeVisible();
  const voiceToggle = page.getByRole("checkbox", {
    name: /^攻略対象のセリフを読み上げる/,
  });
  await expect(voiceToggle).toBeDisabled();
  await expect(
    page.getByText(/設定 > 音声合成 で読み上げを有効にし/),
  ).toBeVisible();
  // BGM の設定は従来どおり同じポップオーバーに残る
  await expect(page.getByText("BGMを再生")).toBeVisible();
});

test("companion mode replaces the day select with a turn budget in setup", async ({
  page,
}) => {
  await enableAdventure(page);
  const state = await mockRomanceApis(page);
  const setupBodies: Record<string, unknown>[] = [];
  await page.route("**/api/adventure/setup/generate", async (route) => {
    setupBodies.push(route.request().postDataJSON() as Record<string, unknown>);
    await route.fulfill({
      json: {
        setting: "大学の学生食堂",
        objective: "20ターン以内にリンと親しくなり、交際を始める",
        constraints: ["リンは昼休みしか会えない"],
      },
    });
  });
  await page.goto("/adventure");
  await page.getByRole("button", { name: /^恋愛シミュレーション/ }).click();

  // 既定は日数セレクト。対面会話モードを ON にするとターン数セレクトに変わる
  await expect(page.getByRole("combobox", { name: /^日数/ })).toBeVisible();
  await page
    .locator(".adventure-setup-generator .adventure-companion-toggle")
    .click();
  await expect(page.getByRole("combobox", { name: /^日数/ })).toHaveCount(0);
  const turnSelect = page.getByRole("combobox", { name: /^ターン数/ });
  await expect(turnSelect).toHaveValue("20");
  await turnSelect.selectOption("30");

  await page.getByRole("button", { name: "ミッション案を自動生成" }).click();
  await expect(page.getByLabel("ゴール")).toHaveValue(
    "20ターン以内にリンと親しくなり、交際を始める",
  );
  expect(setupBodies[0]).toMatchObject({
    scenario_max_turns: 30,
    companion_mode: true,
  });

  await page.getByRole("button", { name: "シナリオを開始" }).click();
  await expect(page).toHaveURL(/\/adventure\/run-1$/);
  expect(state.createBodies[0]).toMatchObject({
    scenario_max_turns: 30,
    companion_mode: true,
  });
});

test("companion mode swaps the partner sprite for the 3D avatar and falls back when it cannot load", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockRomanceApis(page);
  const avatarList = [
    {
      id: "av1",
      name: "Alicia Solid",
      file_size: 1024,
      vrm_spec_version: "0",
      meta: {
        title: "Alicia Solid",
        author: "DWANGO",
        license: "Other",
        license_url: null,
        allowed_user: "Everyone",
        commercial: "Allow",
      },
      file_url: "/avatars/av1/file",
      created_at: "2026-08-28T10:00:00",
    },
  ];
  await page.route("**/api/avatars", async (route) => {
    await route.fulfill({ json: { items: avatarList } });
  });
  // ファイル配信は待たせたままにして、読込中のステージを観察する
  let releaseFile: (() => void) | null = null;
  const fileBlocked = new Promise<void>((resolve) => {
    releaseFile = resolve;
  });
  await page.route("**/api/avatars/av1/file", async (route) => {
    await fileBlocked;
    await route.fulfill({
      status: 404,
      json: { detail: { code: "file_missing", message: "missing" } },
    });
  });
  const companionRun = romanceRunPayload(0, {
    companion_mode: true,
    companion_avatar_id: "av1",
    companion_avatar_url: "/avatars/av1/file",
  });
  await page.route("**/api/adventure/runs/run-1", async (route) => {
    await route.fulfill({ json: companionRun });
  });
  await page.goto("/adventure/run-1");

  // 3D モデル表示中: canvas を持つステージが出て、攻略対象の立ち絵は描かない
  const stage = page.locator(".adventure-stage__frame .adventure-avatar-stage");
  await expect(stage).toBeVisible();
  await expect(stage.locator("canvas")).toHaveCount(1);
  await expect(stage.locator(".adventure-avatar-stage__loading")).toBeVisible();
  await expect(page.getByAltText("攻略対象の立ち絵")).toHaveCount(0);

  // ⚙ には登録済みモデルの選択肢が並び、現在のモデルが選ばれている
  await page.getByRole("button", { name: "画像生成設定" }).click();
  const select = page.locator(
    ".adventure-image-settings-popover .adventure-setup-avatar select",
  );
  await expect(select).toHaveValue("av1");
  await expect(select.locator("option")).toHaveText([
    "なし（立ち絵を表示）",
    "Alicia Solid",
  ]);

  // 読込に失敗したら立ち絵へ戻し、通知で理由を出す
  releaseFile?.();
  await expect(page.getByAltText("攻略対象の立ち絵")).toBeVisible({
    timeout: 15000,
  });
  await expect(stage).toHaveCount(0);
  await expect(page.getByText("3Dモデルを表示できません")).toBeVisible();
});

// 無音の WAV(ヘッダのみ)。読み上げのモック応答に使う
function silentWav(): Buffer {
  const header = Buffer.alloc(44);
  header.write("RIFF", 0);
  header.writeUInt32LE(36, 4);
  header.write("WAVE", 8);
  header.write("fmt ", 12);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22);
  header.writeUInt32LE(8000, 24);
  header.writeUInt32LE(16000, 28);
  header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34);
  header.write("data", 36);
  header.writeUInt32LE(0, 40);
  return header;
}

test("companion avatar keeps the stage uncovered and reads the line at narrative_done", async ({
  page,
}) => {
  await enableAdventure(page);
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "adventure_voice_prefs",
      JSON.stringify({ enabled: true, volume: 0.5, speed: 1 }),
    );
  });
  // 設定画面の TTS を有効・話者ありに固定する(実DBに依存しない)
  await page.route("**/api/settings/user", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    const response = await route.fetch();
    const json = await response.json();
    json.tts_enabled = true;
    json.tts_speaker_id = "spk-1";
    json.tts_style_id = null;
    await route.fulfill({ response, json });
  });
  const synthesizeBodies: Array<Record<string, unknown>> = [];
  await page.route("**/api/aivisspeech/status", async (route) => {
    await route.fulfill({
      json: { process: "running", engine_http: "ok", platform: "linux" },
    });
  });
  await page.route("**/api/aivisspeech/synthesize", async (route) => {
    synthesizeBodies.push(
      route.request().postDataJSON() as Record<string, unknown>,
    );
    await route.fulfill({ contentType: "audio/wav", body: silentWav() });
  });
  await mockRomanceApis(page);
  await page.route("**/api/avatars", async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            id: "av1",
            name: "Alicia Solid",
            file_size: 1024,
            vrm_spec_version: "0",
            meta: {
              title: "Alicia Solid",
              author: "DWANGO",
              license: "Other",
              license_url: null,
              allowed_user: "Everyone",
              commercial: "Allow",
            },
            file_url: "/avatars/av1/file",
            created_at: "2026-08-28T10:00:00",
          },
        ],
      },
    });
  });
  // モデルの読込を保留したままにして、3D ステージ表示中(読込中)の状態を保つ
  let releaseFile: (() => void) | null = null;
  const fileBlocked = new Promise<void>((resolve) => {
    releaseFile = resolve;
  });
  await page.route("**/api/avatars/av1/file", async (route) => {
    await fileBlocked;
    await route.fulfill({
      status: 404,
      json: { detail: { code: "file_missing", message: "missing" } },
    });
  });
  const companionOverrides = {
    companion_mode: true,
    companion_avatar_id: "av1",
    companion_avatar_url: "/avatars/av1/file",
  };
  const companionRun = romanceRunPayload(0, companionOverrides);
  const narrative =
    "美咲は少し驚いた顔をした。\n美咲「こんにちは、ユウヤさん」";
  const turn = {
    id: "turn-1",
    turn_number: 1,
    client_turn_id: "client-1",
    user_input: "美咲に話しかける",
    input_kind: "choice",
    narrative,
    location: "商店街の書店",
    choices: companionRun.choices,
    image_url: null,
    image_status: "not_requested",
    portrait_image_url: null,
    portrait_status: "not_requested",
    created_at: "2026-08-01T00:10:00",
    run_status: "active",
    remaining_turns: 13,
    clues: [],
    completed_milestones: [],
    sim: simPayload({ affection: 13 }),
    partner_expression: "happy",
    partner_gesture: "wave",
  };
  let turnDone = false;
  await page.route("**/api/adventure/runs/run-1", async (route) => {
    await route.fulfill({
      json: turnDone
        ? romanceRunPayload(1, { ...companionOverrides, turns: [turn] })
        : companionRun,
    });
  });

  // route.fulfill は応答を一括で返すため narrative_done と turn の間を観察できない。
  // 実際に流れる SSE サーバへ転送し、本文確定の前後と turn の直前で止める
  let releaseNarrative: (() => void) | null = null;
  let releaseTurn: (() => void) | null = null;
  const narrativeGate = new Promise<void>((resolve) => {
    releaseNarrative = resolve;
  });
  const turnGate = new Promise<void>((resolve) => {
    releaseTurn = resolve;
  });
  const server = createServer((req, res) => {
    let raw = "";
    req.on("data", (chunk: Buffer | string) => {
      raw += chunk.toString();
    });
    req.on("end", () => {
      void (async () => {
        const body = JSON.parse(raw || "{}") as Record<string, unknown>;
        res.writeHead(200, {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
        });
        res.write('event: status\ndata: {"phase":"narrative"}\n\n');
        res.write(
          `event: narrative_chunk\ndata: ${JSON.stringify({
            chunk: "美咲は少し驚いた顔をした。\n",
          })}\n\n`,
        );
        await narrativeGate;
        res.write(
          `event: narrative_chunk\ndata: ${JSON.stringify({
            chunk: "美咲「こんにちは、ユウヤさん」",
          })}\n\n`,
        );
        res.write(
          `event: narrative_done\ndata: ${JSON.stringify({ narrative })}\n\n`,
        );
        res.write('event: status\ndata: {"phase":"clue_check"}\n\n');
        await turnGate;
        turnDone = true;
        res.write(
          `event: turn\ndata: ${JSON.stringify({
            ...turn,
            client_turn_id: String(body.client_turn_id ?? "client-1"),
          })}\n\n`,
        );
        res.write('event: complete\ndata: {"status":"active"}\n\n');
        res.end();
      })();
    });
  });
  await new Promise<void>((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve());
  });
  const { port } = server.address() as AddressInfo;
  await page.route(
    "**/api/adventure/runs/run-1/turns/stream",
    async (route) => {
      await route.continue({ url: `http://127.0.0.1:${port}/turns/stream` });
    },
  );

  try {
    await page.goto("/adventure/run-1");
    await expect(
      page.locator(".adventure-stage__frame .adventure-avatar-stage"),
    ).toBeVisible();
    await page.getByRole("button", { name: /美咲に話しかける/ }).click();

    // 本文ストリーム中: ステージは覆われず、本文のカーソルだけが出る
    await expect(page.getByText("美咲は少し驚いた顔をした。")).toBeVisible();
    await expect(page.locator(".adventure-transcript__caret")).toBeVisible();
    await expect(page.locator(".adventure-stage__loading")).toHaveCount(0);
    await expect(
      page.locator(".adventure-controls .adventure-progress"),
    ).toHaveCount(0);
    expect(synthesizeBodies).toHaveLength(0);

    // 本文確定: turn を待たずに読み上げが始まり、判定の進捗は行動パネルに出る
    releaseNarrative?.();
    await expect.poll(() => synthesizeBodies.length).toBe(1);
    expect(synthesizeBodies[0]).toMatchObject({
      text: "こんにちは、ユウヤさん。",
    });
    await expect(
      page.locator(".adventure-controls .adventure-progress"),
    ).toContainText("行動の結果を判定中");
    await expect(page.locator(".adventure-stage__loading")).toHaveCount(0);
    await expect(page.locator(".adventure-transcript__caret")).toHaveCount(0);
    await expect(page.locator(".adventure-choices")).toHaveCount(0);

    // turn 到着: 選択肢が出て、同じセリフを読み直さない
    releaseTurn?.();
    await expect(page.locator(".adventure-choices")).toBeVisible();
    await expect(
      page.locator(".adventure-controls .adventure-progress"),
    ).toHaveCount(0);
    await expect(page.locator(".adventure-stage__loading")).toHaveCount(0);
    await page.waitForTimeout(500);
    expect(synthesizeBodies).toHaveLength(1);
  } finally {
    releaseFile?.();
    await new Promise<void>((resolve) => {
      server.close(() => resolve());
    });
  }
});

test("a turn in which the partner changes clothes switches the 3D model to the sibling variant", async ({
  page,
}) => {
  await enableAdventure(page);
  const companionOverrides = {
    companion_mode: true,
    companion_avatar_id: "av1",
    companion_avatar_url: "/avatars/av1/file",
  };
  const companionRun = romanceRunPayload(0, companionOverrides);
  await mockRomanceApis(page, companionRun);
  // 同じキャラクター「サクラ」の衣装差分 2 件
  const variant = (id: string, label: string) => ({
    id,
    name: "サクラ",
    character_name: "サクラ",
    variant_label: label,
    file_size: 1024,
    vrm_spec_version: "0",
    meta: {
      title: "サクラ",
      author: "someone",
      license: null,
      license_url: null,
      allowed_user: null,
      commercial: null,
    },
    file_url: `/avatars/${id}/file`,
    created_at: "2026-08-28T10:00:00",
  });
  await page.route("**/api/avatars", async (route) => {
    await route.fulfill({
      json: {
        items: [
          variant("av1", "水着 髪束ねたVer"),
          variant("av2", "ドレス ロングヘアVer"),
        ],
      },
    });
  });
  // モデルの読込は保留し、どのファイルが要求されたかだけを記録する
  const fileRequests: string[] = [];
  let releaseFiles: (() => void) | null = null;
  const filesBlocked = new Promise<void>((resolve) => {
    releaseFiles = resolve;
  });
  await page.route("**/api/avatars/*/file", async (route) => {
    fileRequests.push(new URL(route.request().url()).pathname);
    await filesBlocked;
    await route.fulfill({
      status: 404,
      json: { detail: { code: "file_missing", message: "missing" } },
    });
  });
  const narrative = "美咲は奥で着替えて戻ってきた。\n美咲「どう？似合う？」";
  const turn = {
    id: "turn-1",
    turn_number: 1,
    client_turn_id: "client-1",
    user_input: "美咲に話しかける",
    input_kind: "choice",
    narrative,
    location: "商店街の書店",
    choices: companionRun.choices,
    image_url: null,
    image_status: "not_requested",
    portrait_image_url: null,
    portrait_status: "not_requested",
    created_at: "2026-08-01T00:10:00",
    run_status: "active",
    remaining_turns: 13,
    clues: [],
    completed_milestones: [],
    sim: simPayload({ affection: 13 }),
    partner_expression: "happy",
    partner_gesture: "bounce",
    // 判定が「ドレス」を選んだ手番: この時点のモデルが turn に載る
    companion_avatar_id: "av2",
    companion_avatar_url: "/avatars/av2/file",
  };
  let turnDone = false;
  const switchedOverrides = {
    ...companionOverrides,
    companion_avatar_id: "av2",
    companion_avatar_url: "/avatars/av2/file",
  };
  await page.route("**/api/adventure/runs/run-1", async (route) => {
    await route.fulfill({
      json: turnDone
        ? romanceRunPayload(1, { ...switchedOverrides, turns: [turn] })
        : companionRun,
    });
  });
  await page.route(
    "**/api/adventure/runs/run-1/turns/stream",
    async (route) => {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      turnDone = true;
      const payload = {
        ...turn,
        client_turn_id: String(body.client_turn_id ?? "client-1"),
      };
      await route.fulfill({
        contentType: "text/event-stream",
        body: `event: status\ndata: {"phase":"narrative"}\n\nevent: narrative_done\ndata: ${JSON.stringify(
          { narrative },
        )}\n\nevent: turn\ndata: ${JSON.stringify(payload)}\n\nevent: complete\ndata: {"status":"active"}\n\n`,
      });
    },
  );

  try {
    await page.goto("/adventure/run-1");
    const stage = page.locator(
      ".adventure-stage__frame .adventure-avatar-stage",
    );
    await expect(stage).toBeVisible();
    await expect.poll(() => fileRequests).toEqual(["/api/avatars/av1/file"]);

    // ⚙ の選択肢はキャラクターごとの optgroup に差分ラベルで並び、差分の説明が出る
    await page.getByRole("button", { name: "画像生成設定" }).click();
    const popover = page.locator(".adventure-image-settings-popover");
    const select = popover.locator(".adventure-setup-avatar select");
    await expect(select).toHaveValue("av1");
    await expect(select.locator("optgroup")).toHaveAttribute("label", "サクラ");
    await expect(select.locator("option")).toHaveCount(3);
    await expect(select.locator("optgroup option")).toContainText([
      /Ver$/,
      /Ver$/,
    ]);
    await expect(select).toContainText("水着 髪束ねたVer");
    await expect(select).toContainText("ドレス ロングヘアVer");
    await expect(popover).toContainText("「サクラ」には衣装差分が2種あります");
    await page.getByRole("button", { name: "画像生成設定" }).click();

    // 着替えた手番が届くと、run の再取得を待たずにモデルが差し替わる
    await page.getByRole("button", { name: /美咲に話しかける/ }).click();
    await expect(page.getByText("どう？似合う？")).toBeVisible();
    await expect
      .poll(() => fileRequests.includes("/api/avatars/av2/file"))
      .toBe(true);
    await expect(stage).toBeVisible();
    await page.getByRole("button", { name: "画像生成設定" }).click();
    await expect(
      page.locator(
        ".adventure-image-settings-popover .adventure-setup-avatar select",
      ),
    ).toHaveValue("av2");
  } finally {
    releaseFiles?.();
  }
});
