import { expect, type Page, test } from "@playwright/test";

/**
 * キャラチャット(/talk): 拠点キャラのスレッドを開き、発言をストリーミングで受け、
 * 確定した返答が残り、削除で一覧から消える。バックエンドは SSE 本文ごとモックする。
 */

const BASE_THREAD = {
  id: "base-1",
  kind: "base",
  name: "セレナ",
  pronoun: "私",
  portrait_url: null,
  portrait_missing: true,
  appearance: {
    identity_tags: "1girl, silver hair, green eyes",
    clothing_tags: "purple long dress",
    description: "銀髪に紫のドレス",
    portrait_kind: "standing",
    source: { type: "base" },
  },
  summary_text: null,
  message_count: 0,
  last_message: null,
  language: "ja",
  nsfw_mode: false,
  created_at: "2026-09-06T10:00:00",
  updated_at: "2026-09-06T10:00:00",
};

async function enableCharacterChat(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
    window.localStorage.setItem(
      "app_settings",
      JSON.stringify({ experimentalCharacterChatEnabled: true }),
    );
  });
}

async function mockCharacterChatApis(page: Page) {
  const state = {
    threads: [] as Record<string, unknown>[],
    deleted: [] as string[],
  };
  await page.route("**/api/character-chat/threads", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: { threads: state.threads } });
      return;
    }
    await route.fallback();
  });
  await page.route("**/api/character-chat/threads/base", async (route) => {
    if (!state.threads.some((thread) => thread.id === BASE_THREAD.id)) {
      state.threads.unshift({ ...BASE_THREAD });
    }
    await route.fulfill({ json: BASE_THREAD });
  });
  await page.route("**/api/character-chat/threads/base-1", async (route) => {
    if (route.request().method() === "DELETE") {
      state.deleted.push("base-1");
      state.threads = state.threads.filter((thread) => thread.id !== "base-1");
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    await route.fulfill({ json: { ...BASE_THREAD, messages: [] } });
  });
  return state;
}

test("opens the base character, streams a reply, and deletes the thread", async ({
  page,
}) => {
  await enableCharacterChat(page);
  const state = await mockCharacterChatApis(page);
  const sent: Record<string, unknown>[] = [];
  await page.route(
    "**/api/character-chat/threads/base-1/messages/stream",
    async (route) => {
      sent.push(route.request().postDataJSON() as Record<string, unknown>);
      const done = {
        user_message: {
          id: "u1",
          role: "user",
          content: "最近のやり取りを教えて",
          meta: {},
          created_at: null,
        },
        character_message: {
          id: "c1",
          role: "character",
          content: "最近はメイド服のセッションが多かったですね",
          meta: { lookups: ["recent_sessions"] },
          created_at: null,
        },
        thread: { id: "base-1", message_count: 2, updated_at: null },
      };
      await route.fulfill({
        contentType: "text/event-stream",
        body: `event: status\ndata: {"phase":"plan"}\n\nevent: status\ndata: {"phase":"reply"}\n\nevent: chat_chunk\ndata: {"chunk":"最近は"}\n\nevent: chat_chunk\ndata: {"chunk":"メイド服のセッションが多かったですね"}\n\nevent: chat_done\ndata: ${JSON.stringify(done)}\n\nevent: complete\ndata: {}\n\n`,
      });
    },
  );

  await page.goto("/talk");
  // メニューに項目があり、Hub にセレナのカードが出る
  await expect(
    page.getByRole("button", { name: "キャラチャット", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "キャラチャット" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "セレナと話す" }).click();

  await expect(page).toHaveURL(/\/talk\/base-1$/);
  await expect(page.getByRole("heading", { name: /セレナ/ })).toBeVisible();
  // 同梱画像が無いので案内と「立ち絵を生成」が出る
  await expect(page.getByText(/serena\.png/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "立ち絵を生成" }),
  ).toBeVisible();

  const input = page.getByRole("textbox", { name: "セレナに話しかける" });
  await input.fill("最近のやり取りを教えて");
  await page.getByRole("button", { name: "送信" }).click();

  await expect(
    page.getByText("最近はメイド服のセッションが多かったですね"),
  ).toBeVisible();
  await expect(page.getByText("調べたこと: 最近のセッション")).toBeVisible();
  expect(sent).toEqual([{ content: "最近のやり取りを教えて" }]);
  await expect(input).toHaveValue("");

  // 削除は確認ダイアログを経て一覧へ戻る
  await page.getByRole("button", { name: "この会話を削除" }).click();
  await page.getByRole("button", { name: "削除する" }).click();
  await expect(page).toHaveURL(/\/talk$/);
  expect(state.deleted).toEqual(["base-1"]);
  await expect(page.getByText("まだ会話はありません。")).toBeVisible();
});

test("redirects to /play/new when the feature is off", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
  });
  await page.goto("/talk");
  await expect(page).toHaveURL(/\/play\/new$/);
});
