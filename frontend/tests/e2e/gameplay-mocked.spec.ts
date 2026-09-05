/**
 * 通常プレイ画面(GamePlayScreen)のモック済み E2E。
 * バックエンド無しで、エクスポート・会話ストリーム・メッセージ削除/修正の
 * 画面側の振る舞いを固定する(Phase 3-5 の分解前後で同じ結果になること)。
 */
import { expect, type Locator, type Page, test } from "@playwright/test";

const sessionId = "44444444-4444-4444-8444-444444444444";

function baseHistory() {
  return [
    {
      id: "hist-1",
      instruction: "最初の着替え",
      image_url: "/history/images/hist-1",
      feeling_text: "最初の心境",
      after_description: "first",
      timestamp: "2026-08-09T10:00:00+09:00",
      instruction_type: "dress_up",
    },
    {
      id: "hist-2",
      instruction: "赤いドレスに変える",
      image_url: "/history/images/hist-2",
      feeling_text: "二つ目の心境",
      after_description: "second",
      timestamp: "2026-08-09T10:02:00+09:00",
      instruction_type: "reality_alter",
    },
  ];
}

function baseConversation() {
  return [
    {
      id: "conv-user-1",
      role: "user",
      content: "こんにちは",
      created_at: "2026-08-09T10:01:00+09:00",
      instruction_type: "conversation",
    },
    {
      id: "conv-char-1",
      role: "character",
      content: "やあ、元気？",
      created_at: "2026-08-09T10:01:05+09:00",
      instruction_type: null,
    },
  ];
}

interface MockState {
  history: ReturnType<typeof baseHistory>;
  conversation: ReturnType<typeof baseConversation>;
  stats: { bloom: number; shame: number; adaptation: number };
  deletedHistory: string[];
  deletedConversations: string[];
  latestHistoryDeletes: number;
  chatStreamUrls: string[];
  restoreCount: number;
  attributes: Array<{ id: string; text: string }>;
  addedAttributes: string[];
  removedAttributes: string[];
  aivisStops: number;
  previewBodies: Array<Record<string, unknown>>;
}

async function mockPlaySession(
  page: Page,
  options: { ttsEnabled?: boolean; imageProvider?: string } = {},
): Promise<MockState> {
  const state: MockState = {
    history: baseHistory(),
    conversation: baseConversation(),
    stats: { bloom: 30, shame: 20, adaptation: 5 },
    deletedHistory: [],
    deletedConversations: [],
    latestHistoryDeletes: 0,
    chatStreamUrls: [],
    restoreCount: 0,
    attributes: [{ id: "attr-1", text: "猫耳" }],
    addedAttributes: [],
    removedAttributes: [],
    aivisStops: 0,
    previewBodies: [],
  };
  await page.addInitScript(() => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
    window.localStorage.setItem("novelai_opus_confirmed", "true");
  });
  await page.route("**/health", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        status: "ok",
        image_provider: options.imageProvider ?? "novelai",
        image_description_provider: "novelai",
        feeling_provider: "novelai",
      },
    });
  });
  await page.route("**/api/settings/user", async (route) => {
    if (route.request().method() !== "GET") {
      await route.fulfill({ status: 200, json: {} });
      return;
    }
    await route.fulfill({
      status: 200,
      json: {
        nsfw_mode: false,
        difficulty: "normal",
        language: "ja",
        novelai_image_model: "nai-diffusion-4-5-full",
        novelai_curated_image_model: "nai-diffusion-4-5-curated",
        tts_enabled: options.ttsEnabled ?? false,
      },
    });
  });
  await page.route("**/api/settings", async (route) => {
    await route.fulfill({ status: 200, json: {} });
  });
  await page.route("**/api/settings/self-profile", async (route) => {
    await route.fulfill({ status: 200, json: {} });
  });
  await page.route("**/api/memory/text", async (route) => {
    await route.fulfill({ status: 200, json: { text: "" } });
  });
  await page.route("**/api/game/characters", async (route) => {
    await route.fulfill({ status: 200, json: { characters: [] } });
  });
  await page.route("**/api/game/anlas", async (route) => {
    await route.fulfill({
      status: 200,
      json: { total_anlas: 120, fixed_anlas: 100, purchased_anlas: 20 },
    });
  });
  await page.route("**/api/favorites?*", async (route) => {
    await route.fulfill({
      status: 200,
      json: { items: [], total: 0, page: 1, page_size: 100, has_more: false },
    });
  });
  await page.route("**/api/history/images/*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="#345"/></svg>',
    });
  });
  // 復元(sessions/*/restore)と現在セッション取得(game/session)は同じ内容を返す。
  // 後者は「修正して再生成」後の再同期(App.handleSessionStart)が呼ぶ
  const sessionPayload = () => ({
    session_id: sessionId,
    character_id: "mock-character",
    current_image_url: state.history.at(-1)?.image_url ?? null,
    transformation_count: state.history.length,
    history: state.history,
    stats: { ...state.stats, nsfw_mode: false },
    attributes: state.attributes.map((attr) => ({
      id: attr.id,
      text: attr.text,
    })),
    conversation_history: state.conversation,
  });
  await page.route("**/api/game/session", async (route) => {
    if (route.request().method() !== "GET") {
      await route.fulfill({ status: 200, json: { success: true } });
      return;
    }
    state.restoreCount += 1;
    await route.fulfill({ status: 200, json: sessionPayload() });
  });
  await page.route("**/api/game/sessions/*/restore", async (route) => {
    state.restoreCount += 1;
    await route.fulfill({
      status: 200,
      json: {
        session_id: sessionId,
        character_id: "mock-character",
        current_image_url: state.history.at(-1)?.image_url ?? null,
        transformation_count: state.history.length,
        history: state.history,
        stats: { ...state.stats, nsfw_mode: false },
        attributes: state.attributes.map((attr) => ({
          id: attr.id,
          text: attr.text,
        })),
        conversation_history: state.conversation,
      },
    });
  });
  await page.route("**/api/game/sessions/*/play-memory", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        system_enabled: false,
        user_enabled: false,
        system_text: "",
        user_text: "",
        system_updated_at: null,
      },
    });
  });
  await page.route("**/api/game/history/*", async (route) => {
    const url = new URL(route.request().url());
    const historyId = decodeURIComponent(url.pathname.split("/").pop() ?? "");
    state.deletedHistory.push(historyId);
    state.history = state.history.filter((item) => item.id !== historyId);
    await route.fulfill({
      status: 200,
      json: {
        success: true,
        deleted_history_id: historyId,
        restored_history_id: state.history.at(-1)?.id ?? "",
        parameter_reverts: [
          { stat_name: "bloom", delta: -10, prev_value: 30, new_value: 20 },
        ],
      },
    });
  });
  await page.route("**/api/game/conversation/message/*", async (route) => {
    const url = new URL(route.request().url());
    const conversationId = decodeURIComponent(
      url.pathname.split("/").pop() ?? "",
    );
    state.deletedConversations.push(conversationId);
    await route.fulfill({
      status: 200,
      json: { success: true, deleted_conversation_id: conversationId },
    });
  });
  await page.route("**/api/game/session/*/latest-history", async (route) => {
    state.latestHistoryDeletes += 1;
    const removed = state.history.pop();
    await route.fulfill({
      status: 200,
      json: {
        success: true,
        deleted_history_id: removed?.id ?? "",
        restored_instruction: removed?.instruction ?? "",
        restored_instruction_type: removed?.instruction_type ?? "dress_up",
        current_image_path: "",
        restored_history_id: state.history.at(-1)?.id ?? "",
      },
    });
  });
  await page.route("**/api/game/chat/stream?*", async (route) => {
    state.chatStreamUrls.push(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        'data: {"type":"text","chunk":"モックの"}',
        "",
        'data: {"type":"text","chunk":"返事です"}',
        "",
        'data: {"type":"done","user_conversation_id":"conv-user-2","character_conversation_id":"conv-char-2"}',
        "",
      ].join("\n"),
    });
  });
  await page.route("**/api/game/attributes?*", async (route) => {
    const url = new URL(route.request().url());
    const text = url.searchParams.get("attribute_text") ?? "";
    state.addedAttributes.push(text);
    const id = `attr-${state.addedAttributes.length + 1}`;
    state.attributes.push({ id, text });
    await route.fulfill({
      status: 200,
      json: { attribute: { id, attribute_text: text, text } },
    });
  });
  await page.route("**/api/game/attributes/*", async (route) => {
    const id = route.request().url().split("/").pop() ?? "";
    state.removedAttributes.push(id);
    await route.fulfill({ status: 200, json: { success: true } });
  });
  await page.route("**/api/aivisspeech/status", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        platform: "windows",
        process: state.aivisStops > 0 ? "stopped" : "running",
        engine_http: state.aivisStops > 0 ? "error" : "ok",
      },
    });
  });
  await page.route("**/api/aivisspeech/stop-engine", async (route) => {
    state.aivisStops += 1;
    await route.fulfill({ status: 200, json: { ok: true } });
  });
  await page.route("**/api/game/preview/prompt", async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    state.previewBodies.push(body);
    await route.fulfill({
      status: 200,
      json: {
        image_edit_prompt: "1girl, red dress, night city",
        feeling_system_prompt: "system prompt",
        feeling_user_prompt: "user prompt",
        novelai_tag_prompt: null,
        surroundings_system_prompt: null,
        surroundings_user_prompt: null,
      },
    });
  });
  return state;
}

async function gotoSession(page: Page) {
  await page.goto(`/play/${sessionId}`);
  await expect(page.locator(".game-play-screen__content")).toBeVisible();
}

// メッセージの操作ボタンはホバー中だけ pointer-events が有効になる
async function clickMessageAction(message: Locator, actionClass: string) {
  await message.hover();
  await message.locator(actionClass).click();
}

async function openRightPanel(page: Page) {
  const toggle = page.locator(".main-layout__toggle-right");
  if ((await toggle.getAttribute("aria-expanded")) !== "true") {
    await toggle.click();
  }
  await expect(page.locator(".right-panel")).toBeVisible();
}

test.describe("通常プレイ画面(モック)", () => {
  test("履歴と会話を時系列で復元し、Anlas バーを出す", async ({ page }) => {
    await mockPlaySession(page);
    await gotoSession(page);

    const messages = page.locator(".chat-message");
    // 履歴2件 × (指示 + 心境) + 会話2件 = 6
    await expect(messages).toHaveCount(6);
    await expect(messages.nth(0)).toContainText("最初の着替え");
    await expect(messages.nth(1)).toContainText("最初の心境");
    await expect(messages.nth(2)).toContainText("こんにちは");
    await expect(messages.nth(3)).toContainText("やあ、元気？");
    await expect(messages.nth(4)).toContainText("赤いドレスに変える");
    await expect(messages.nth(5)).toContainText("二つ目の心境");
    await expect(page.locator(".game-play-screen__anlas-label")).toHaveText(
      "Anlas: 120",
    );
    await expect(page.locator(".game-play-screen__anlas-detail")).toContainText(
      "(100 + 20)",
    );
  });

  test("エクスポートメニューから Markdown をダウンロードできる", async ({
    page,
  }) => {
    await mockPlaySession(page);
    await gotoSession(page);

    const exportButton = page.locator(".chat-export-header__btn");
    await exportButton.click();
    const menu = page.locator(".chat-export-header__menu");
    await expect(menu).toBeVisible();
    await expect(menu.getByRole("button")).toHaveCount(7);

    const downloadPromise = page.waitForEvent("download");
    await menu.getByRole("button", { name: "Markdown (.md)" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(
      /^chat_\d{4}-\d{2}-\d{2}_44444444\.md$/,
    );
    await expect(menu).toBeHidden();

    // 外側クリックで閉じる
    await exportButton.click();
    await expect(menu).toBeVisible();
    await page.locator(".game-play-screen__left-panel").click({
      position: { x: 4, y: 4 },
    });
    await expect(menu).toBeHidden();
  });

  test("会話は chat/stream をストリームしてキャラクターの返事を積む", async ({
    page,
  }) => {
    const state = await mockPlaySession(page);
    await gotoSession(page);

    await page.locator(".chat-input__type-select").selectOption("conversation");
    await page.locator(".chat-input__textarea").fill("今日は何する？");
    await page.locator(".chat-input__send-btn").click();

    const messages = page.locator(".chat-message");
    await expect(messages).toHaveCount(8);
    await expect(messages.nth(6)).toContainText("今日は何する？");
    await expect(messages.nth(7)).toContainText("モックの返事です");
    await expect(messages.nth(7)).not.toHaveClass(/chat-message--streaming/);

    expect(state.chatStreamUrls).toHaveLength(1);
    const url = new URL(state.chatStreamUrls[0]);
    expect(url.searchParams.get("session_id")).toBe(sessionId);
    expect(url.searchParams.get("message")).toBe("今日は何する？");
    expect(url.searchParams.get("language")).toBe("ja");
    expect(url.searchParams.get("use_history_lookback")).toBe("true");

    // 返事が確定したので、会話メッセージの削除ボタンが有効になる
    const lastUser = page.locator(".chat-message--user").last();
    await expect(
      lastUser.locator(".chat-message__action-btn--delete"),
    ).toBeEnabled();
  });

  test("画像付きメッセージの削除は履歴 API を呼び、応答ごと消してパラメータを戻す", async ({
    page,
  }) => {
    const state = await mockPlaySession(page);
    await gotoSession(page);

    const target = page
      .locator(".chat-message--user")
      .filter({ hasText: "赤いドレスに変える" });
    await clickMessageAction(target, ".chat-message__action-btn--delete");

    const dialog = page.getByRole("dialog", { name: "メッセージを削除" });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("二つ目の心境");
    await dialog.getByRole("button", { name: "削除する" }).click();

    await expect(dialog).toBeHidden();
    expect(state.deletedHistory).toEqual(["hist-2"]);
    const messages = page.locator(".chat-message");
    await expect(messages).toHaveCount(4);
    await expect(page.getByText("赤いドレスに変える")).toHaveCount(0);
    await expect(page.getByText("二つ目の心境")).toHaveCount(0);
    // parameter_reverts が stats に反映される(bloom 30 → 20)
    await expect(
      page.locator(".character-state-panel__stat-fill--bloom"),
    ).toHaveAttribute("style", /width: 20%/);
  });

  test("会話メッセージの削除は会話 API をユーザー分と返答分で呼ぶ", async ({
    page,
  }) => {
    const state = await mockPlaySession(page);
    await gotoSession(page);

    const target = page
      .locator(".chat-message--user")
      .filter({ hasText: "こんにちは" });
    await clickMessageAction(target, ".chat-message__action-btn--delete");
    const dialog = page.getByRole("dialog", { name: "メッセージを削除" });
    await expect(dialog).toContainText("やあ、元気？");
    await dialog.getByRole("button", { name: "削除する" }).click();

    await expect(dialog).toBeHidden();
    expect(state.deletedConversations).toEqual(["conv-user-1", "conv-char-1"]);
    await expect(page.locator(".chat-message")).toHaveCount(4);
    await expect(page.getByText("やあ、元気？")).toHaveCount(0);
  });

  test("最新メッセージの修正は最新履歴を削除して指示と種別を入力欄へ戻す", async ({
    page,
  }) => {
    const state = await mockPlaySession(page);
    await gotoSession(page);

    const latest = page.locator(".chat-message--user").last();
    await expect(latest).toContainText("赤いドレスに変える");
    await clickMessageAction(latest, ".chat-message__action-btn--edit");

    const dialog = page.getByRole("dialog", { name: "修正して再生成" });
    await expect(dialog).toContainText("赤いドレスに変える");
    await dialog.getByRole("button", { name: "取り消して修正する" }).click();

    await expect(dialog).toBeHidden();
    expect(state.latestHistoryDeletes).toBe(1);
    await expect(page.locator(".chat-input__textarea")).toHaveValue(
      "赤いドレスに変える",
    );
    await expect(page.locator(".chat-input__type-select")).toHaveValue(
      "reality_alter",
    );
    // セッションを再同期し、残った履歴だけでメッセージを組み直す
    await expect.poll(() => state.restoreCount).toBeGreaterThan(1);
    await expect(page.locator(".chat-message")).toHaveCount(4);
  });
});

test.describe("右パネル(モック)", () => {
  test("属性の追加と削除を API に送り、サマリーへ反映する", async ({
    page,
  }) => {
    const state = await mockPlaySession(page);
    await gotoSession(page);
    await openRightPanel(page);

    const panel = page.locator(".right-panel");
    await expect(panel.locator(".right-panel__attribute-badge")).toHaveText([
      /猫耳/,
    ]);
    await panel.getByRole("button", { name: "➕ 追加" }).click();
    const input = panel.locator(".right-panel__attribute-input input");
    await input.fill("眼鏡");
    await input.press("Enter");

    await expect(panel.locator(".right-panel__attribute-badge")).toHaveCount(2);
    expect(state.addedAttributes).toEqual(["眼鏡"]);
    await expect(panel.locator(".right-panel__summary")).toContainText(
      "猫耳, 眼鏡",
    );

    await panel
      .locator(".right-panel__attribute-badge")
      .first()
      .getByRole("button", { name: /削除/ })
      .click();
    await expect(panel.locator(".right-panel__attribute-badge")).toHaveCount(1);
    expect(state.removedAttributes).toEqual(["attr-1"]);
  });

  test("NovelAI 設定のスライダーとプロンプトビルダーが動く", async ({
    page,
  }) => {
    await mockPlaySession(page);
    await gotoSession(page);
    await openRightPanel(page);
    const panel = page.locator(".right-panel");

    await expect(panel.getByText("NovelAI 画像設定")).toBeVisible();
    const sliders = panel.locator(".right-panel__slider");
    await sliders.first().fill("0.5");
    await expect(panel.getByText("i2i強度: 0.50")).toBeVisible();

    // 衣装色の一貫性を ON にするとプロンプトビルダーが現れる
    await panel
      .locator(".right-panel__toggle")
      .filter({ hasText: "服の色の一貫性を保つ" })
      .locator(".right-panel__toggle-switch")
      .click();
    await expect(
      panel.getByRole("heading", { name: "プロンプトビルダー" }),
    ).toBeVisible();
    await panel.locator(".right-panel__mini-label input").nth(0).fill("彼女");
    await panel.locator(".right-panel__mini-label input").nth(2).fill("制服");
    await panel.getByRole("button", { name: "📝 指示として利用" }).click();
    await expect(page.locator(".chat-input__textarea")).toHaveValue(
      "彼女、制服で",
    );

    // 自由入力へ切り替えて内容が localStorage に残る
    await panel.getByRole("button", { name: "⌨️ 自由入力に切り替え" }).click();
    await panel.locator(".right-panel__textarea").last().fill("自由文");
    await expect
      .poll(() =>
        page.evaluate(() => {
          const raw = window.localStorage.getItem("prompt_builder");
          return raw ? JSON.parse(raw) : null;
        }),
      )
      .toMatchObject({ mode: "textarea", who: "彼女", freeform: "自由文" });
  });

  test("音声合成エンジンの状態を表示して停止できる", async ({ page }) => {
    const state = await mockPlaySession(page, { ttsEnabled: true });
    await gotoSession(page);
    await openRightPanel(page);
    const section = page.locator(".right-panel__aivis-engine");

    await expect(section).toContainText("起動中");
    await section.getByRole("button", { name: "停止" }).click();
    await expect.poll(() => state.aivisStops).toBe(1);
    await expect(section).toContainText("停止中");
    await expect(section.getByRole("button", { name: "起動" })).toBeVisible();
  });

  test("プロンプトプレビューを取得し、編集したプロンプトで送信する", async ({
    page,
  }) => {
    const state = await mockPlaySession(page);
    const playBodies: Array<Record<string, unknown>> = [];
    await page.route("**/api/game/play/stream", async (route) => {
      playBodies.push(
        route.request().postDataJSON() as Record<string, unknown>,
      );
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          "event: complete",
          'data: {"history_id":"hist-3","transformation_count":3}',
          "",
        ].join("\n"),
      });
    });
    await page.addInitScript(() => {
      window.localStorage.setItem(
        "app_settings",
        JSON.stringify({ rightPanelOpen: true }),
      );
    });
    await page.route("**/api/game/sessions/*/restore", async (route) => {
      await route.fulfill({
        status: 200,
        json: {
          session_id: sessionId,
          character_id: "mock-character",
          current_image_url: "/history/images/hist-2",
          transformation_count: 2,
          history: baseHistory(),
          stats: {
            bloom: 30,
            shame: 20,
            adaptation: 5,
            nsfw_mode: false,
            enable_prompt_preview: true,
          },
          attributes: [],
          conversation_history: [],
        },
      });
    });
    await gotoSession(page);
    await openRightPanel(page);
    const panel = page.locator(".right-panel");

    await page.locator(".chat-input__textarea").fill("夜の街へ出かける");
    await panel.getByRole("button", { name: "🔍 プレビュー生成" }).click();
    const edit = panel.locator(".right-panel__preview-result textarea").first();
    await expect(edit).toHaveValue("1girl, red dress, night city");
    expect(state.previewBodies[0]).toMatchObject({
      session_id: sessionId,
      instruction: "夜の街へ出かける",
      instruction_type: "dress_up",
    });

    await edit.fill("1girl, blue dress");
    await panel
      .getByRole("button", { name: "📤 このプロンプトで送信" })
      .click();
    await expect.poll(() => playBodies.length).toBe(1);
    expect(playBodies[0]).toMatchObject({
      instruction: "夜の街へ出かける",
      prompt_override: "1girl, blue dress",
    });
    await expect(panel.locator(".right-panel__preview-result")).toHaveCount(0);
  });
});
