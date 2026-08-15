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

test("precise reference shows an Anlas confirmation before submitting a turn", async ({
  page,
}) => {
  await enableAdventure(page);
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
