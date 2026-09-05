import { expect, type Page, test } from "@playwright/test";

/**
 * 遊び方ガイド: サイドメニューの常設項目から既定OFFの機能を紹介し、
 * その場でONにするとメニューへ項目が現れる。
 */

async function bootstrap(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
  });
  // ONにした後の遷移先(TSFシナリオのハブ)が空一覧で描けるよう最小限モックする
  await page.route("**/api/adventure/templates", async (route) => {
    await route.fulfill({ json: { templates: [] } });
  });
  await page.route("**/api/adventure/runs", async (route) => {
    await route.fulfill({ json: { runs: [] } });
  });
  await page.route("**/api/avatars", async (route) => {
    await route.fulfill({ json: { items: [] } });
  });
}

test("enabling play memory with a stale session does not warn", async ({
  page,
}) => {
  await bootstrap(page);
  // localStorage に残った古いセッションIDはバックエンドに存在せず 404 になる
  await page.addInitScript(() => {
    window.localStorage.setItem("current_session_id", "stale-session-1");
  });
  await page.route("**/api/game/sessions/*/play-memory", async (route) => {
    await route.fulfill({ status: 404, json: { detail: "session not found" } });
  });
  await page.goto("/guide");

  const memoryCard = page.locator(".guide-screen__card").filter({
    has: page.getByRole("heading", { name: "プレイメモ" }),
  });
  await memoryCard.locator(".guide-screen__toggle").click();
  await expect(
    memoryCard.getByText("通常プレイの右パネルに「プレイメモ」が表示されます"),
  ).toBeVisible();
  // 404(存在しないセッション)への同期失敗は警告トーストを出さない
  await page.waitForTimeout(700);
  await expect(page.locator(".notification-toast")).toHaveCount(0);
});

test("guide screen enables TSF Scenario and adds it to the menu", async ({
  page,
}) => {
  await bootstrap(page);
  await page.goto("/achievements");

  // 未読ドット付きの「遊び方ガイド」が常設され、TSFシナリオはまだ無い
  const guideItem = page.getByRole("button", { name: "遊び方ガイド" });
  await expect(guideItem).toBeVisible();
  await expect(page.locator(".side-menu__dot")).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "TSFシナリオ", exact: true }),
  ).toHaveCount(0);

  // ガイドを開くとドットが消える
  await guideItem.click();
  await expect(page).toHaveURL(/\/guide$/);
  await expect(
    page.getByRole("heading", { name: "遊び方ガイド" }),
  ).toBeVisible();
  await expect(page.locator(".side-menu__dot")).toHaveCount(0);

  // 対面会話カードは、親機能がOFFの間は有効化を促すボタンを出す
  const talkCard = page.locator(".guide-screen__card").filter({
    has: page.getByRole("heading", { name: "トークと対面会話モード" }),
  });
  await expect(
    talkCard.getByRole("button", { name: "まずTSFシナリオを有効にする" }),
  ).toBeVisible();

  // TSFシナリオカードのトグルでONにすると、メニューに項目が現れる
  const adventureCard = page.locator(".guide-screen__card").filter({
    has: page.getByRole("heading", { name: "TSFシナリオ", exact: true }),
  });
  await adventureCard.locator(".guide-screen__toggle").click();
  await expect(
    page.getByRole("button", { name: "TSFシナリオ", exact: true }),
  ).toBeVisible();
  await expect(
    adventureCard.getByText("メニューに追加されました"),
  ).toBeVisible();
  await expect(
    talkCard.getByRole("button", { name: "TSFシナリオを開く" }),
  ).toBeVisible();

  // カードの「開く」でそのままTSFシナリオへ移動できる
  await adventureCard
    .getByRole("button", { name: "TSFシナリオを開く" })
    .click();
  await expect(page).toHaveURL(/\/adventure$/);

  // 再読込しても設定は保存されている(ドットも再表示されない)
  await page.goto("/guide");
  await expect(
    adventureCard.getByText("メニューに追加されました"),
  ).toBeVisible();
  await expect(page.locator(".side-menu__dot")).toHaveCount(0);
});

test("guide screen lists the inventory system card", async ({ page }) => {
  await bootstrap(page);
  await page.goto("/guide");

  const card = page.locator(".guide-screen__card").filter({
    has: page.getByRole("heading", { name: "持ち物システム" }),
  });
  await expect(card).toBeVisible();
  await expect(card).toContainText("シナリオの進行方法に大きな影響があります");
  // 親機能(TSFシナリオ)が OFF の間は有効化を促す
  await expect(
    card.getByRole("button", { name: "まずTSFシナリオを有効にする" }),
  ).toBeVisible();
});
