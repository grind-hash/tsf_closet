import { expect, test } from "@playwright/test";

test.describe("新しい設定画面（検索とカテゴリ）", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      if (!window.sessionStorage.getItem("settings_search_test_initialized")) {
        window.localStorage.removeItem("app_settings");
        window.sessionStorage.removeItem("settings_active_category");
        window.sessionStorage.setItem(
          "settings_search_test_initialized",
          "true",
        );
      }
      window.localStorage.setItem("novelai_api_key_consent", "true");
    });
    // 文言で確かめるため、表示言語を日本語に固定する
    await page.route("**/api/settings/user", async (route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      const response = await route.fetch();
      const json = await response.json();
      await route.fulfill({ response, json: { ...json, language: "ja" } });
    });
    await page.goto("/settings");
    await expect(page.locator(".settings-screen")).toBeVisible();
  });

  test("トグルで切り替え、カテゴリと検索で項目を絞り込む", async ({ page }) => {
    const toggleLabel = page.locator("label.settings-screen__header-toggle");
    const toggle = toggleLabel.getByRole("checkbox", {
      name: /新しい設定画面を利用/,
    });

    // 既定は従来の画面
    await expect(toggle).not.toBeChecked();
    await expect(page.locator(".settings-v2")).toHaveCount(0);
    await expect(page.getByTestId("settings-avatar-toggle")).toBeVisible();

    await toggleLabel.click();
    await expect(toggle).toBeChecked();

    const nav = page.getByRole("navigation", { name: "設定のカテゴリ" });
    const content = page.locator(".settings-v2__content");
    const sectionHeadings = content.getByRole("heading", { level: 2 });
    await expect(nav).toBeVisible();
    await expect(sectionHeadings).toHaveText(["ゲーム設定"]);

    // カテゴリを切り替える
    await nav.getByRole("button", { name: "表示設定" }).click();
    await expect(sectionHeadings).toHaveText(["表示設定"]);
    // 実験的機能から移した「画像とチャットを連動」を含めて3件
    await expect(content.locator(".settings-screen__item")).toHaveCount(3);

    // 開閉セクションは、v2 では開いた状態で出す
    await nav.getByRole("button", { name: /3Dモデル/ }).click();
    await expect(page.getByTestId("settings-avatar-toggle")).toHaveCount(0);
    await expect(page.getByTestId("avatar-drop-zone")).toBeVisible();
    await nav.getByRole("button", { name: "表示設定" }).click();

    // ひらがなで入力しても、カタカナのラベルに一致する
    const search = page.getByRole("searchbox", { name: "設定項目を検索" });
    await search.fill("ふぉんと");
    await expect(sectionHeadings).toHaveText(["表示設定"]);
    await expect(content.locator(".settings-screen__item")).toHaveCount(1);
    await expect(
      content.getByText("アプリ全体の表示フォントを変更します"),
    ).toBeVisible();
    await expect(nav.getByRole("button", { name: /表示設定/ })).toContainText(
      "1",
    );

    // Esc で入力を消すと、選択中のカテゴリに戻る
    await search.press("Escape");
    await expect(search).toHaveValue("");
    await expect(sectionHeadings).toHaveText(["表示設定"]);
    await expect(content.locator(".settings-screen__item")).toHaveCount(3);

    // 一致しないときは案内を出し、そこから検索をクリアできる
    await search.fill("zzzz");
    const empty = page.getByRole("status");
    await expect(empty).toContainText("「zzzz」に一致する設定はありません");
    await expect(sectionHeadings).toHaveCount(0);
    await empty.getByRole("button", { name: "検索をクリア" }).click();
    await expect(search).toHaveValue("");
    await expect(sectionHeadings).toHaveText(["表示設定"]);

    // 開き直すと選択中のカテゴリを復元し、そこへフォーカスを移す
    await page.reload();
    await expect(sectionHeadings).toHaveText(["表示設定"]);
    await expect(nav.getByRole("button", { name: "表示設定" })).toBeFocused();

    // トグルを OFF にすると従来の画面に戻る
    await toggleLabel.click();
    await expect(toggle).not.toBeChecked();
    await expect(page.locator(".settings-v2")).toHaveCount(0);
    await expect(page.getByTestId("settings-avatar-toggle")).toBeVisible();
  });

  test("項目の分け直し・セグメント型・ショートカット・ハイライト", async ({
    page,
  }) => {
    await page.locator("label.settings-screen__header-toggle").click();
    const nav = page.getByRole("navigation", { name: "設定のカテゴリ" });
    const content = page.locator(".settings-v2__content");
    await expect(nav).toBeVisible();

    // 択一選択はセグメント型で、選んでいる選択肢の説明だけを出す
    const difficulty = content.getByRole("radiogroup", { name: "難易度" });
    await expect(difficulty).toBeVisible();
    await expect(difficulty.getByRole("radio")).toHaveCount(3);
    await expect(content.locator(".settings-screen__radio")).toHaveCount(0);

    // 実験的機能から移した項目は、役割に合うカテゴリに出る
    await nav.getByRole("button", { name: "画像生成" }).click();
    await expect(content.getByText("衣装の重なりを考慮")).toBeVisible();
    await nav.getByRole("button", { name: /Experimental/ }).click();
    await expect(content.getByText("衣装の重なりを考慮")).toHaveCount(0);
    await expect(
      content.locator(".settings-screen__item", { hasText: "プレイメモ" }),
    ).toBeVisible();

    // "/" で検索欄へ移る（カテゴリボタンにフォーカスがある状態から）
    const search = page.getByRole("searchbox", { name: "設定項目を検索" });
    await nav.getByRole("button", { name: "表示設定" }).focus();
    await page.keyboard.press("/");
    await expect(search).toBeFocused();
    await expect(search).toHaveValue("");

    // 一致した文字をハイライトする
    await search.fill("ふぉんと");
    await expect
      .poll(() =>
        page.evaluate(() => CSS.highlights.get("settings-search")?.size ?? 0),
      )
      .toBeGreaterThan(0);
    await search.press("Escape");
    await expect
      .poll(() => page.evaluate(() => CSS.highlights.has("settings-search")))
      .toBe(false);

    // Ctrl+K でも検索欄へ移る
    await nav.getByRole("button", { name: "表示設定" }).focus();
    await page.keyboard.press("Control+k");
    await expect(search).toBeFocused();
  });
});
