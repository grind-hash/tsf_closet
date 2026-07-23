import { expect, test, type Locator, type Page } from "@playwright/test";

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

async function openPreciseReferenceSettings(page: Page): Promise<Locator> {
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

  await page.goto("/play");
  await page.locator(".backdrop").first().waitFor({ state: "hidden" });
  await page.getByRole("button", { name: /パネルを開く|Open panel/i }).click();

  const dropZone = page.getByTestId("precise-ref-drop-zone");
  await expect(dropZone).toBeVisible();
  await dropZone.scrollIntoViewIfNeeded();
  return dropZone;
}

async function dropFiles(page: Page, dropZone: Locator, files: TestFile[]) {
  const items = files.map((file) => ({
    name: file.name,
    mimeType: file.mimeType,
    bytes: file.buffer ? [...file.buffer] : null,
    size: file.size ?? null,
  }));
  const dataTransfer = await page.evaluateHandle((inputFiles) => {
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

  await dropZone.dispatchEvent("dragenter", { dataTransfer });
  await expect(dropZone).toHaveClass(/is-dragging/);
  await dropZone.dispatchEvent("dragover", { dataTransfer });
  await dropZone.dispatchEvent("drop", { dataTransfer });
  await expect(dropZone).not.toHaveClass(/is-dragging/);
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
