/**
 * spec 004 (T027, US4): 履歴遡及件数（history_lookback_count）設定 UI E2E
 *
 * 要件:
 *   - 設定画面で履歴遡及件数を 10 → 15 へ変更
 *   - 設定保存後、PUT /api/settings に history_lookback_count: 15 が送信される
 *   - 範囲外（4 / 21）入力は UI で 5 / 20 に丸められる
 *
 * 注: 本テストは live スタック（フロント:3000 / バック:8000）が必要。
 */

import { expect, test } from "@playwright/test";

const APP_URL = "http://localhost:3000";

test.describe("history lookback count setting", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("novelai_api_key_consent", "true");
    });
  });

  test("select targets with backward-compatible defaults and persist them", async ({
    page,
  }) => {
    await page.goto(APP_URL);
    await page.locator(".backdrop").first().waitFor({ state: "hidden" });
    await page
      .getByRole("button", { name: /設定|Settings/i })
      .first()
      .click();

    const targetGroup = page.getByRole("group", {
      name: /履歴遡及を利用する対象|Use History Lookback For/i,
    });
    const action = targetGroup.getByLabel(/行動|Action/i, { exact: true });
    const conversation = targetGroup.getByLabel(/会話|Conversation/i, {
      exact: true,
    });
    const dressUp = targetGroup.getByLabel(/着せ替え|Dress Up/i, {
      exact: true,
    });
    const realityAlter = targetGroup.getByLabel(
      /現実改変|Reality Alteration/i,
      { exact: true },
    );

    await expect(action).toBeChecked();
    await expect(conversation).toBeChecked();
    await expect(dressUp).not.toBeChecked();
    await expect(realityAlter).not.toBeChecked();

    await action.uncheck();
    await dressUp.check();
    await realityAlter.check();
    await page.reload();

    const restoredGroup = page.getByRole("group", {
      name: /履歴遡及を利用する対象|Use History Lookback For/i,
    });
    await expect(
      restoredGroup.getByLabel(/行動|Action/i, { exact: true }),
    ).not.toBeChecked();
    await expect(
      restoredGroup.getByLabel(/会話|Conversation/i, { exact: true }),
    ).toBeChecked();
    await expect(
      restoredGroup.getByLabel(/着せ替え|Dress Up/i, { exact: true }),
    ).toBeChecked();
    await expect(
      restoredGroup.getByLabel(/現実改変|Reality Alteration/i, {
        exact: true,
      }),
    ).toBeChecked();
  });

  test("update lookback count from 10 to 15", async ({ page }) => {
    const updateRequests: Array<{ url: string; body: unknown }> = [];

    page.on("request", (request) => {
      if (
        request.method() === "PUT" &&
        request.url().includes("/api/settings") &&
        !request.url().includes("/api/settings/user") &&
        !request.url().includes("/api/settings/self-profile")
      ) {
        try {
          updateRequests.push({
            url: request.url(),
            body: JSON.parse(request.postData() ?? "{}"),
          });
        } catch {
          /* 解析できないリクエストは対象外 */
        }
      }
    });

    await page.goto(APP_URL);
    await page.locator(".backdrop").first().waitFor({ state: "hidden" });

    await page
      .getByRole("button", { name: /設定|Settings/i })
      .first()
      .click();

    const lookbackInput = page.getByLabel(/履歴遡及件数|History Lookback/i);
    await expect(lookbackInput).toBeVisible();

    await lookbackInput.fill("15");
    await lookbackInput.blur();

    await expect
      .poll(() =>
        updateRequests.some(
          (req) =>
            (req.body as { history_lookback_count?: number })
              ?.history_lookback_count === 15,
        ),
      )
      .toBe(true);
  });

  test("clamp out-of-range input", async ({ page }) => {
    await page.goto(APP_URL);
    await page.locator(".backdrop").first().waitFor({ state: "hidden" });
    await page
      .getByRole("button", { name: /設定|Settings/i })
      .first()
      .click();

    const lookbackInput = page.getByLabel(/履歴遡及件数|History Lookback/i);

    await lookbackInput.fill("21");
    await lookbackInput.blur();
    await expect(lookbackInput).toHaveValue("20");

    await lookbackInput.fill("4");
    await lookbackInput.blur();
    await expect(lookbackInput).toHaveValue("5");
  });

  test("send selected target flags for every operation and preview", async ({
    page,
  }) => {
    const sessionId = "88888888-8888-4888-8888-888888888888";
    const playRequests: Array<{
      instruction_type?: string;
      use_history_lookback?: boolean;
    }> = [];
    const chatFlags: boolean[] = [];
    const previewRequests: Array<{
      instruction_type?: string;
      use_history_lookback?: boolean;
    }> = [];

    await page.addInitScript(() => {
      window.localStorage.setItem(
        "app_settings",
        JSON.stringify({
          historyLookbackTargets: {
            action: false,
            conversation: true,
            dress_up: true,
            reality_alter: false,
          },
        }),
      );
    });
    await page.route("**/api/game/characters", async (route) => {
      await route.fulfill({ status: 200, json: { characters: [] } });
    });
    await page.route("**/api/game/sessions/*/restore", async (route) => {
      await route.fulfill({
        status: 200,
        json: {
          session_id: sessionId,
          character_id: "history-lookback-character",
          current_image_url: null,
          transformation_count: 0,
          history: [],
          stats: {
            bloom: 0,
            shame: 0,
            adaptation: 0,
            nsfw_mode: false,
            enable_prompt_preview: true,
          },
          attributes: [],
          conversation_history: [],
        },
      });
    });
    await page.route("**/api/game/play/stream", async (route) => {
      playRequests.push(route.request().postDataJSON());
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          "event: text",
          'data: {"chunk":"確認"}',
          "",
          "event: complete",
          `data: {"session_id":"${sessionId}","transformation_count":1}`,
          "",
        ].join("\n"),
      });
    });
    await page.route("**/api/game/chat/stream?*", async (route) => {
      const url = new URL(route.request().url());
      chatFlags.push(url.searchParams.get("use_history_lookback") === "true");
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          'data: {"type":"text","chunk":"確認"}',
          "",
          'data: {"type":"done"}',
          "",
        ].join("\n"),
      });
    });
    await page.route("**/api/game/preview/prompt", async (route) => {
      previewRequests.push(route.request().postDataJSON());
      await route.fulfill({
        status: 200,
        json: {
          image_edit_prompt: "image",
          feeling_system_prompt: "system",
          feeling_user_prompt: "user",
          instruction_type: "reality_alter",
          novelai_tag_prompt: null,
        },
      });
    });

    const sendInstruction = async (
      instructionType: "action" | "conversation" | "dress_up" | "reality_alter",
    ) => {
      await page.goto(`${APP_URL}/play/${sessionId}`);
      await expect(page.locator(".game-play-screen")).toBeVisible();
      await page.locator(".backdrop").first().waitFor({ state: "hidden" });
      await page
        .locator(".chat-input__type-select")
        .selectOption(instructionType);
      await page
        .locator(".chat-input__textarea")
        .fill(`${instructionType} test`);
      await page.locator(".chat-input__send-btn").click();
    };

    await sendInstruction("action");
    await expect.poll(() => playRequests.length).toBe(1);
    await sendInstruction("dress_up");
    await expect.poll(() => playRequests.length).toBe(2);
    await sendInstruction("reality_alter");
    await expect.poll(() => playRequests.length).toBe(3);
    await sendInstruction("conversation");
    await expect.poll(() => chatFlags.length).toBe(1);

    expect(playRequests).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          instruction_type: "action",
          use_history_lookback: false,
        }),
        expect.objectContaining({
          instruction_type: "dress_up",
          use_history_lookback: true,
        }),
        expect.objectContaining({
          instruction_type: "reality_alter",
          use_history_lookback: false,
        }),
      ]),
    );
    expect(chatFlags).toEqual([true]);

    await page.goto(`${APP_URL}/play/${sessionId}`);
    await expect(page.locator(".game-play-screen")).toBeVisible();
    await page.locator(".backdrop").first().waitFor({ state: "hidden" });
    await page
      .locator(".chat-input__type-select")
      .selectOption("reality_alter");
    await page.locator(".chat-input__textarea").fill("preview test");
    await page
      .getByRole("button", { name: /パネルを開く|Open panel/i })
      .click();
    await page
      .getByRole("button", { name: /プレビュー生成|Generate Preview/i })
      .click();
    await expect.poll(() => previewRequests.length).toBe(1);
    expect(previewRequests[0]).toMatchObject({
      instruction_type: "reality_alter",
      use_history_lookback: false,
    });
  });
});
