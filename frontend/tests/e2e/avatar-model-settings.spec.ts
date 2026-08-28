import { expect, type Page, test } from "@playwright/test";

/**
 * 設定画面「3Dモデル (VRM)」セクション。
 * 一覧・バッジ・削除アイコン・アップロードのエラー文言を API モックで確認する。
 * 実 VRM の描画(WebGL)には依存しない。
 */

function avatarPayload(overrides: Record<string, unknown> = {}) {
  return {
    id: "av1",
    name: "Alicia Solid",
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

  await expect(page.getByText("3Dモデル (VRM)")).toBeVisible();
  const rows = page.locator(".avatar-settings__row");
  await expect(rows).toHaveCount(2);
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
  await page.getByRole("button", { name: "削除" }).first().click();
  await expect(page.locator(".avatar-settings__row")).toHaveCount(0);
  expect(deleted).toBe(true);
});
