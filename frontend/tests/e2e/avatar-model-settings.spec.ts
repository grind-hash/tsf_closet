import { expect, type Page, test } from "@playwright/test";

/**
 * 設定画面「3Dモデル (VRM)」セクション。
 * 一覧・バッジ・削除アイコン・アップロードのエラー文言を API モックで確認する。
 * 実 VRM の描画(WebGL)には依存しない。
 * セクションは既定で閉じている(最下部のアコーディオン)ため、各テストは
 * openAvatarSection で開いてから中身を確認する。
 */

function avatarPayload(overrides: Record<string, unknown> = {}) {
  return {
    id: "av1",
    name: "Alicia Solid",
    character_name: null,
    variant_label: null,
    file_size: 7878712,
    vrm_spec_version: "0",
    meta: {
      title: "Alicia Solid",
      author: "© DWANGO Co., Ltd.",
      license: "Other",
      license_url: "https://example.com/rule",
      allowed_user: "Everyone",
      commercial: "Allow",
    },
    file_url: "/avatars/av1/file",
    created_at: "2026-08-28T10:00:00",
    ...overrides,
  };
}

/** 最下部のアコーディオンを開く(既定は閉じている) */
async function openAvatarSection(page: Page) {
  const toggle = page.getByTestId("settings-avatar-toggle");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
}

async function mockAvatarList(page: Page, items: unknown[]) {
  await page.route("**/api/avatars", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: { items } });
      return;
    }
    await route.fallback();
  });
}

test("registered models are listed with metadata, spec badge and delete icon", async ({
  page,
}) => {
  await mockAvatarList(page, [
    avatarPayload(),
    avatarPayload({
      id: "av2",
      name: "Sample 1.0",
      vrm_spec_version: "1",
      meta: {
        title: "Sample 1.0",
        author: "A, B",
        license: "VRM Public License 1.0",
        license_url: "https://vrm.dev/licenses/1.0/",
        allowed_user: "everyone",
        commercial: "personalProfit",
      },
    }),
  ]);
  await page.goto("/settings");

  // 既定では閉じていて、見出しに件数の要約だけが出る
  const toggle = page.getByTestId("settings-avatar-toggle");
  await expect(toggle).toContainText("3Dモデル (VRM)");
  await expect(toggle).toContainText("登録 2件・キャラクター 0");
  const rows = page.locator(".avatar-settings__row");
  await expect(rows).toHaveCount(2);
  await expect(rows.first()).toBeHidden();
  // 「3Dモデル」はリセットの直前(最下部)に置く
  await expect(
    page.locator(
      ".settings-screen__section--collapsible + .settings-screen__section--danger",
    ),
  ).toHaveCount(1);
  await openAvatarSection(page);
  await expect(rows.first()).toBeVisible();
  await expect(rows.nth(0)).toContainText("Alicia Solid");
  await expect(rows.nth(0)).toContainText("© DWANGO Co., Ltd.");
  await expect(rows.nth(0).locator(".avatar-settings__badge")).toHaveText(
    "VRM 0.x",
  );
  await expect(rows.nth(1).locator(".avatar-settings__badge")).toHaveText(
    "VRM 1.0",
  );
  // ライセンスは配布元の URL へのリンクになる
  await expect(
    rows.nth(1).getByRole("link", { name: "VRM Public License 1.0" }),
  ).toHaveAttribute("href", "https://vrm.dev/licenses/1.0/");
  // 削除はギャラリー式のアイコンボタン(赤塗りのテキストボタンにしない)
  await expect(rows.nth(0).getByRole("button", { name: "削除" })).toHaveClass(
    /prompt-expander__icon-btn/,
  );
  await expect(page.getByTestId("avatar-drop-zone")).toBeVisible();
});

test("empty state and upload errors are explained", async ({ page }) => {
  await mockAvatarList(page, []);
  let uploadStatus = 400;
  await page.route("**/api/avatars", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    if (uploadStatus === 400) {
      await route.fulfill({
        status: 400,
        json: {
          detail: {
            code: "invalid_vrm",
            message: "VRM ファイルではありません",
          },
        },
      });
    } else {
      await route.fulfill({
        status: 413,
        json: {
          detail: {
            code: "file_too_large",
            message: "ファイルが大きすぎます(上限 128 MiB)",
          },
        },
      });
    }
  });
  await page.goto("/settings");
  await expect(page.getByTestId("settings-avatar-toggle")).toContainText(
    "登録済みのモデルはありません",
  );
  await openAvatarSection(page);
  await expect(
    page.getByText("登録済みの3Dモデルはありません。"),
  ).toBeVisible();

  const input = page.locator(
    'input[type="file"][accept=".vrm,model/gltf-binary"]',
  );
  await input.setInputFiles({
    name: "broken.vrm",
    mimeType: "model/gltf-binary",
    buffer: Buffer.from("not a vrm"),
  });
  await expect(page.getByRole("alert")).toContainText(
    "VRMファイルではありません",
  );

  uploadStatus = 413;
  await input.setInputFiles({
    name: "huge.vrm",
    mimeType: "model/gltf-binary",
    buffer: Buffer.from("x".repeat(64)),
  });
  await expect(page.getByRole("alert")).toContainText("ファイルが大きすぎます");
  // 一覧は空のまま
  await expect(page.locator(".avatar-settings__row")).toHaveCount(0);
});

test("deleting a model asks for confirmation and removes the row", async ({
  page,
}) => {
  await mockAvatarList(page, [avatarPayload()]);
  let deleted = false;
  await page.route("**/api/avatars/av1", async (route) => {
    if (route.request().method() === "DELETE") {
      deleted = true;
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    await route.fallback();
  });
  page.on("dialog", (dialog) => {
    expect(dialog.message()).toContain("Alicia Solid");
    void dialog.accept();
  });
  await page.goto("/settings");
  await openAvatarSection(page);
  await page.getByRole("button", { name: "削除" }).first().click();
  await expect(page.locator(".avatar-settings__row")).toHaveCount(0);
  expect(deleted).toBe(true);
});

test("models of the same character are grouped and an existing model can be regrouped", async ({
  page,
}) => {
  await mockAvatarList(page, [
    avatarPayload({
      id: "k1",
      name: "サクラ",
      character_name: "サクラ",
      variant_label: "水着 髪束ねたVer",
    }),
    avatarPayload({
      id: "k2",
      name: "サクラ",
      character_name: "サクラ",
      variant_label: "ドレス ロングヘアVer",
    }),
    avatarPayload(),
  ]);
  let patched: unknown = null;
  await page.route("**/api/avatars/av1", async (route) => {
    if (route.request().method() === "PATCH") {
      patched = route.request().postDataJSON();
      await route.fulfill({
        json: avatarPayload({
          character_name: "サクラ",
          variant_label: "制服",
        }),
      });
      return;
    }
    await route.fallback();
  });
  await page.goto("/settings");
  await expect(page.getByTestId("settings-avatar-toggle")).toContainText(
    "登録 3件・キャラクター 1",
  );
  await openAvatarSection(page);

  // 分類済みグループが先、未分類は末尾。キャラクターは既定で閉じている
  const groups = page.getByTestId("avatar-group");
  await expect(groups).toHaveCount(2);
  const sakura = groups.nth(0);
  await expect(sakura.locator(".avatar-settings__group-title")).toHaveText(
    "サクラ",
  );
  await expect(sakura).toContainText("2種の差分");
  await expect(sakura.locator(".avatar-settings__row")).toHaveCount(2);
  await expect(sakura.locator(".avatar-settings__row").first()).toBeHidden();
  const groupToggle = sakura.getByRole("button", { name: "サクラ" });
  await expect(groupToggle).toHaveAttribute("aria-expanded", "false");
  await groupToggle.click();
  await expect(groupToggle).toHaveAttribute("aria-expanded", "true");
  await expect(sakura.locator(".avatar-settings__row").first()).toBeVisible();
  await expect(sakura).toContainText("着替えの場面に合わせて");
  // グループ内の行は差分ラベルで見せ、モデル名は副次的に添える
  await expect(sakura.locator(".avatar-settings__name")).toContainText([
    /Ver$/,
    /Ver$/,
  ]);
  await expect(sakura).toContainText("水着 髪束ねたVer");
  await expect(sakura).toContainText("ドレス ロングヘアVer");
  await expect(
    sakura.locator(".avatar-settings__subname").first(),
  ).toContainText("サクラ");
  await expect(
    sakura.getByRole("button", { name: "キャラクター名を変更" }),
  ).toBeVisible();
  const ungrouped = groups.nth(1);
  await expect(ungrouped.locator(".avatar-settings__group-title")).toHaveText(
    "キャラクター未設定",
  );
  await expect(ungrouped.locator(".avatar-settings__name")).toHaveText(
    "Alicia Solid",
  );

  // 未分類のモデルを削除せずに同じキャラクターへ付け替える
  await ungrouped.getByRole("button", { name: "キャラクターを編集" }).click();
  const editor = page.getByTestId("avatar-character-editor");
  await expect(editor).toBeVisible();
  // 既存のキャラクター名は datalist で候補になる
  await expect(
    page.locator("datalist#avatar-character-names option"),
  ).toHaveAttribute("value", "サクラ");
  await editor.getByLabel("キャラクター名").fill("サクラ");
  await editor.getByLabel("差分の説明").fill("制服");
  await editor.getByRole("button", { name: "保存" }).click();

  await expect(groups).toHaveCount(1);
  await expect(groups.nth(0).locator(".avatar-settings__row")).toHaveCount(3);
  await expect(groups.nth(0)).toContainText("3種の差分");
  await expect(groups.nth(0)).toContainText("制服");
  expect(patched).toEqual({ character_name: "サクラ", variant_label: "制服" });

  // 開閉状態はブラウザに保存され、再読込後も開いたまま
  await page.reload();
  await expect(page.getByTestId("settings-avatar-toggle")).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  await expect(
    page
      .getByTestId("avatar-group")
      .nth(0)
      .getByRole("button", { name: "サクラ" }),
  ).toHaveAttribute("aria-expanded", "true");
});

test("several VRM files can be dropped at once and are registered in order", async ({
  page,
}) => {
  await mockAvatarList(page, []);
  const uploadedNames: string[] = [];
  await page.route("**/api/avatars", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    const body = route.request().postData() ?? "";
    const match = body.match(/filename="([^"]+)"/);
    const name = match?.[1] ?? "unknown";
    uploadedNames.push(name);
    const stem = name.replace(/\.vrm$/i, "");
    const [character, ...rest] = stem.split("_");
    await route.fulfill({
      status: 201,
      json: avatarPayload({
        id: `up${uploadedNames.length}`,
        name: stem,
        character_name: rest.length > 0 ? character : null,
        variant_label: rest.length > 0 ? rest.join(" ") : null,
      }),
    });
  });
  await page.goto("/settings");
  await openAvatarSection(page);
  const input = page.locator(
    'input[type="file"][accept=".vrm,model/gltf-binary"]',
  );
  await expect(input).toHaveAttribute("multiple", "");
  await input.setInputFiles([
    {
      name: "サクラ_水着_髪束ねたVer.vrm",
      mimeType: "model/gltf-binary",
      buffer: Buffer.from("glTF"),
    },
    {
      name: "サクラ_ドレス_ロングヘアVer.vrm",
      mimeType: "model/gltf-binary",
      buffer: Buffer.from("glTF"),
    },
  ]);
  const group = page.getByTestId("avatar-group");
  await expect(group).toHaveCount(1);
  await expect(group.locator(".avatar-settings__group-title")).toHaveText(
    "サクラ",
  );
  await expect(group.locator(".avatar-settings__row")).toHaveCount(2);
  expect(uploadedNames).toEqual([
    "サクラ_水着_髪束ねたVer.vrm",
    "サクラ_ドレス_ロングヘアVer.vrm",
  ]);
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("auto-classify fills only unset models from their names and opens the new group", async ({
  page,
}) => {
  // 更新前に登録したモデル相当: 名前は規則に合うが未分類。手入力済みは変えない
  const legacy = avatarPayload({
    id: "old1",
    name: "サクラ_水着_髪束ねたVer",
  });
  const decided = avatarPayload({
    id: "old2",
    name: "サクラ_ドレス",
    character_name: "別名",
    variant_label: "手入力",
  });
  await mockAvatarList(page, [legacy, decided, avatarPayload()]);
  let classifyCalls = 0;
  await page.route("**/api/avatars/auto-classify", async (route) => {
    classifyCalls += 1;
    await route.fulfill({
      json: {
        updated: 1,
        updated_ids: ["old1"],
        items: [
          {
            ...legacy,
            character_name: "サクラ",
            variant_label: "水着 髪束ねたVer",
          },
          decided,
          avatarPayload(),
        ],
      },
    });
  });
  await page.goto("/settings");
  await openAvatarSection(page);
  const groups = page.getByTestId("avatar-group");
  await expect(groups).toHaveCount(2);
  await expect(
    groups.nth(0).locator(".avatar-settings__group-title"),
  ).toHaveText("別名");

  await page.getByRole("button", { name: "ファイル名から自動分類" }).click();
  await expect(page.locator(".avatar-settings__notice")).toContainText(
    "1件を分類しました。",
  );
  expect(classifyCalls).toBe(1);
  await expect(groups).toHaveCount(3);
  // 新しく分類されたグループは開いた状態で結果を見せる
  const sakura = groups.filter({ hasText: "サクラ" }).first();
  await expect(sakura.getByRole("button", { name: "サクラ" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  await expect(sakura.locator(".avatar-settings__name")).toHaveText(
    "水着 髪束ねたVer",
  );
  // 手入力済みのグループは閉じたまま変わらない
  const decidedGroup = groups.filter({ hasText: "別名" }).first();
  await expect(
    decidedGroup.getByRole("button", { name: "別名" }),
  ).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByTestId("settings-avatar-toggle")).toContainText(
    "登録 3件・キャラクター 2",
  );
});
