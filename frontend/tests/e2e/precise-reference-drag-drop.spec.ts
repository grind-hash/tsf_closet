import {
  expect,
  type JSHandle,
  type Locator,
  type Page,
  test,
} from "@playwright/test";

const PNG_BYTES = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);

type TestFile = {
  name: string;
  mimeType: string;
  buffer?: Buffer;
  size?: number;
};

// 実DBのユーザー設定(V5選択中など)に依存しないよう、画像モデルをV4.5に固定する
// (V5実効時は精密参照セクションが無効化されるため)
const V45_USER_SETTINGS: Record<string, unknown> = {
  novelai_image_model: "nai-diffusion-4-5-full",
  novelai_curated_image_model: "nai-diffusion-4-5-curated",
};

// nsfw OFF 既定のため curated 側を V5 にすると実効モデルが V5 になる
const V5_USER_SETTINGS: Record<string, unknown> = {
  nsfw_mode: false,
  novelai_curated_image_model: "nai-diffusion-5-curated",
};

async function preparePlayPage(
  page: Page,
  userSettings: Record<string, unknown> = V45_USER_SETTINGS,
) {
  await page.addInitScript(() => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
    window.localStorage.setItem("novelai_opus_confirmed", "true");
  });
  await page.route("**/health", async (route) => {
    const response = await route.fetch();
    const json = await response.json();
    json.image_provider = "novelai";
    await route.fulfill({ response, json });
  });
  await page.route("**/api/settings/user", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    const response = await route.fetch();
    const json = await response.json();
    Object.assign(json, userSettings);
    await route.fulfill({ response, json });
  });

  await page.goto("/play");
  await page.locator(".backdrop").first().waitFor({ state: "hidden" });
}

async function openRightPanel(page: Page) {
  await page.getByRole("button", { name: /パネルを開く|Open panel/i }).click();
}

// 右パネルの開閉は localStorage に残るため、閉じた状態を明示的に作る
async function ensureRightPanelClosed(page: Page): Promise<Locator> {
  const toggle = page.locator(".main-layout__toggle-right");
  if ((await toggle.getAttribute("aria-expanded")) === "true") {
    await toggle.click();
  }
  const panel = page.locator(".main-layout__right-panel");
  await expect(panel).not.toHaveClass(/is-open/);
  return panel;
}

async function openPreciseReferenceSettings(page: Page): Promise<Locator> {
  await preparePlayPage(page);
  await openRightPanel(page);

  const dropZone = page.getByTestId("precise-ref-drop-zone");
  await expect(dropZone).toBeVisible();
  await dropZone.scrollIntoViewIfNeeded();
  return dropZone;
}

async function createDataTransfer(
  page: Page,
  files: TestFile[],
): Promise<JSHandle<DataTransfer>> {
  const items = files.map((file) => ({
    name: file.name,
    mimeType: file.mimeType,
    bytes: file.buffer ? [...file.buffer] : null,
    size: file.size ?? null,
  }));
  return page.evaluateHandle((inputFiles) => {
    const transfer = new DataTransfer();
    for (const inputFile of inputFiles) {
      const bytes =
        inputFile.bytes === null
          ? new Uint8Array(inputFile.size ?? 0)
          : new Uint8Array(inputFile.bytes);
      transfer.items.add(
        new File([bytes], inputFile.name, { type: inputFile.mimeType }),
      );
    }
    return transfer;
  }, items);
}

async function dropFiles(page: Page, dropZone: Locator, files: TestFile[]) {
  const dataTransfer = await createDataTransfer(page, files);

  await dropZone.dispatchEvent("dragenter", { dataTransfer });
  await expect(dropZone).toHaveClass(/is-dragging/);
  await dropZone.dispatchEvent("dragover", { dataTransfer });
  await dropZone.dispatchEvent("drop", { dataTransfer });
  await expect(dropZone).not.toHaveClass(/is-dragging/);
  await dataTransfer.dispose();
}

// 画面のどこか（ここではメインコンテンツ）へ画像をドロップする
async function dropFilesOnScreen(page: Page, files: TestFile[]) {
  const content = page.locator(".main-layout__content");
  const overlay = page.getByTestId("precise-ref-drop-overlay");
  const dataTransfer = await createDataTransfer(page, files);

  await content.dispatchEvent("dragenter", { dataTransfer });
  await expect(overlay).toBeVisible();
  await content.dispatchEvent("dragover", { dataTransfer });
  await content.dispatchEvent("drop", { dataTransfer });
  await expect(overlay).toBeHidden();
  await dataTransfer.dispose();
}

test.describe("精密参照画像の追加", () => {
  test("クリック選択と単一画像のドロップで画像を追加できる", async ({
    page,
  }) => {
    const dropZone = await openPreciseReferenceSettings(page);

    const fileChooserPromise = page.waitForEvent("filechooser");
    await dropZone.click();
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles({
      name: "selected.png",
      mimeType: "image/png",
      buffer: PNG_BYTES,
    });
    await expect(page.getByText("selected.png")).toBeVisible();

    await dropFiles(page, dropZone, [
      { name: "dropped.png", mimeType: "image/png", buffer: PNG_BYTES },
    ]);
    await expect(page.getByText("dropped.png")).toBeVisible();
    // ドロップゾーンでの処理と画面全体ドロップが二重に追加しない
    await expect(page.locator(".right-panel__precise-ref-card")).toHaveCount(2);
  });

  test("複数画像を順番に最大6枚まで追加する", async ({ page }) => {
    const dropZone = await openPreciseReferenceSettings(page);
    const files = Array.from({ length: 7 }, (_, index) => ({
      name: `reference-${index + 1}.png`,
      mimeType: "image/png",
      buffer: PNG_BYTES,
    }));

    await dropFiles(page, dropZone, files);

    const cards = page.locator(".right-panel__precise-ref-card");
    await expect(cards).toHaveCount(6);
    for (let index = 0; index < 6; index += 1) {
      await expect(cards.nth(index)).toContainText(
        `reference-${index + 1}.png`,
      );
    }
    await expect(
      page.getByText(/参照画像は最大6枚までです|Up to 6 reference images/),
    ).toBeVisible();
  });

  test("不正形式と容量超過を拒否し、有効な画像は追加する", async ({ page }) => {
    const dropZone = await openPreciseReferenceSettings(page);

    await dropFiles(page, dropZone, [
      { name: "invalid.gif", mimeType: "image/gif", buffer: PNG_BYTES },
      { name: "valid.png", mimeType: "image/png", buffer: PNG_BYTES },
    ]);
    await expect(page.locator(".right-panel__precise-ref-card")).toHaveCount(1);
    await expect(page.getByText("valid.png")).toBeVisible();
    await expect(
      page.getByText(/invalid\.gif: PNG, JPEG, WebP|invalid\.gif: Only PNG/),
    ).toBeVisible();

    await dropFiles(page, dropZone, [
      {
        name: "oversized.png",
        mimeType: "image/png",
        size: 10 * 1024 * 1024 + 1,
      },
    ]);
    await expect(page.locator(".right-panel__precise-ref-card")).toHaveCount(1);
    await expect(
      page.getByText(
        /oversized\.png: ファイルサイズ|oversized\.png: File size/,
      ),
    ).toBeVisible();
  });
});

test.describe("画面全体への画像ドロップ", () => {
  test("画面のどこにドロップしても精密参照画像に追加され、右パネルが開いてセクションが見える", async ({
    page,
  }) => {
    await preparePlayPage(page);
    const panel = await ensureRightPanelClosed(page);

    const overlay = page.getByTestId("precise-ref-drop-overlay");
    const content = page.locator(".main-layout__content");
    const dataTransfer = await createDataTransfer(page, [
      { name: "anywhere.png", mimeType: "image/png", buffer: PNG_BYTES },
    ]);

    // ドラッグ中は薄いオーバーレイに追加先の案内が出る
    await content.dispatchEvent("dragenter", { dataTransfer });
    await expect(overlay).toBeVisible();
    await expect(overlay).toContainText(
      /精密参照画像に追加|precise reference image/,
    );
    await content.dispatchEvent("dragover", { dataTransfer });
    await content.dispatchEvent("drop", { dataTransfer });
    await dataTransfer.dispose();

    await expect(overlay).toBeHidden();
    await expect(panel).toHaveClass(/is-open/);
    const cards = page.locator(".right-panel__precise-ref-card");
    await expect(cards).toHaveCount(1);
    await expect(cards.first()).toContainText("anywhere.png");
    await expect(
      page.getByTestId("precise-reference-section"),
    ).toBeInViewport();
  });

  test("ドラッグを途中でやめるとオーバーレイが消える", async ({ page }) => {
    await preparePlayPage(page);
    const overlay = page.getByTestId("precise-ref-drop-overlay");
    const content = page.locator(".main-layout__content");
    const dataTransfer = await createDataTransfer(page, [
      { name: "cancelled.png", mimeType: "image/png", buffer: PNG_BYTES },
    ]);

    await content.dispatchEvent("dragenter", { dataTransfer });
    await expect(overlay).toBeVisible();
    await content.dispatchEvent("dragleave", { dataTransfer });
    await expect(overlay).toBeHidden();
    await dataTransfer.dispose();
    await expect(page.locator(".right-panel__precise-ref-card")).toHaveCount(0);
  });

  test("不正形式だけをドロップすると通知が出て追加されず、右パネルも開かない", async ({
    page,
  }) => {
    await preparePlayPage(page);
    const panel = await ensureRightPanelClosed(page);

    await dropFilesOnScreen(page, [
      { name: "invalid.gif", mimeType: "image/gif", buffer: PNG_BYTES },
    ]);

    await expect(
      page.locator(".notification-toast").filter({
        hasText: /invalid\.gif: PNG, JPEG, WebP|invalid\.gif: Only PNG/,
      }),
    ).toBeVisible();
    await expect(panel).not.toHaveClass(/is-open/);
    await expect(page.locator(".right-panel__precise-ref-card")).toHaveCount(0);
  });
});

test.describe("V5モデル選択時の精密参照", () => {
  test("実効モデルがV5のとき精密参照は無効化され説明が表示される", async ({
    page,
  }) => {
    await preparePlayPage(page, V5_USER_SETTINGS);
    await openRightPanel(page);

    // 説明文言が表示され、操作ブロックが無効化されている
    await expect(
      page.getByText(
        /V5モデルでは精密参照は利用できません|not available with V5/,
      ),
    ).toBeVisible();
    const disabledBlock = page.locator(".right-panel__disabled-block");
    await expect(disabledBlock).toBeVisible();
    await expect(
      disabledBlock.getByTestId("precise-ref-drop-zone"),
    ).toBeVisible();
  });

  test("実効モデルがV5のとき画面ドロップは利用不可の案内を出して追加しない", async ({
    page,
  }) => {
    await preparePlayPage(page, V5_USER_SETTINGS);
    await ensureRightPanelClosed(page);

    const overlay = page.getByTestId("precise-ref-drop-overlay");
    const content = page.locator(".main-layout__content");
    const dataTransfer = await createDataTransfer(page, [
      { name: "v5.png", mimeType: "image/png", buffer: PNG_BYTES },
    ]);

    await content.dispatchEvent("dragenter", { dataTransfer });
    await expect(overlay).toBeVisible();
    await expect(overlay).toHaveClass(/is-unavailable/);
    await expect(overlay).toContainText(
      /V5モデルでは精密参照は利用できません|not available with V5/,
    );
    await content.dispatchEvent("drop", { dataTransfer });
    await dataTransfer.dispose();

    await expect(overlay).toBeHidden();
    await expect(
      page.locator(".notification-toast").filter({
        hasText: /V5モデルでは精密参照は利用できません|not available with V5/,
      }),
    ).toBeVisible();
    await expect(page.locator(".right-panel__precise-ref-card")).toHaveCount(0);
  });
});
