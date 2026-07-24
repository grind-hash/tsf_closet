import { expect, test, type Page } from "@playwright/test";

const sessionId = "11111111-1111-4111-8111-111111111111";

const history = Array.from({ length: 5 }, (_, index) => ({
  id: `history-${index + 1}`,
  instruction: `衣装変更 ${index + 1}`,
  image_url: `/history/images/history-${index + 1}`,
  feeling_text: `変身後の文章 ${index + 1}`,
  after_description: `変身後の状態 ${index + 1}`,
  timestamp: `2026-07-23T12:0${index}:00+09:00`,
  instruction_type: "dress_up",
}));

async function mockActiveSession(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
    window.localStorage.setItem("novelai_opus_confirmed", "true");
  });

  await page.route("**/api/game/characters", async (route) => {
    await route.fulfill({ status: 200, json: { characters: [] } });
  });

  await page.route("**/api/game/anlas", async (route) => {
    await route.fulfill({
      status: 200,
      json: { total_anlas: 3862, fixed_anlas: 3378, purchased_anlas: 484 },
    });
  });

  await page.route("**/api/game/sessions/*/restore", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        session_id: sessionId,
        character_id: "mobile-layout-character",
        current_image_url: history.at(-1)?.image_url,
        transformation_count: history.length,
        history,
        stats: {
          bloom: 20,
          shame: 40,
          adaptation: 10,
          nsfw_mode: true,
        },
        attributes: [],
        conversation_history: [],
      },
    });
  });

  await page.route("**/api/history/images/*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: [
        '<svg xmlns="http://www.w3.org/2000/svg" width="768" height="1344" viewBox="0 0 768 1344">',
        '<rect width="768" height="1344" fill="#1b3158"/>',
        '<circle cx="384" cy="380" r="180" fill="#64b5f6"/>',
        '<rect x="170" y="570" width="428" height="650" rx="180" fill="#ef9a9a"/>',
        "</svg>",
      ].join(""),
    });
  });
}

async function expectImageAndChatVisible(
  page: Page,
  minimumImageHeight: number,
) {
  const leftPanel = page.locator(".game-play-screen__left-panel");
  const chatArea = page.locator(".game-play-screen__chat-area");
  const imageButton = page.locator(".character-state-panel__image-btn");
  const historyStrip = page.locator(".character-state-panel__history-strip");
  const historyNav = page.locator(".character-state-panel__nav-full");
  const chatInput = page.locator(".chat-input__textarea");

  await expect(leftPanel).toBeVisible();
  await expect(imageButton).toBeVisible();
  await expect(historyStrip).toBeAttached();
  await expect(historyNav).toBeAttached();
  await expect(chatInput).toBeVisible();

  const [leftBox, chatBox, imageBox, inputBox] = await Promise.all([
    leftPanel.boundingBox(),
    chatArea.boundingBox(),
    imageButton.boundingBox(),
    chatInput.boundingBox(),
  ]);

  expect(leftBox).not.toBeNull();
  expect(chatBox).not.toBeNull();
  expect(imageBox).not.toBeNull();
  expect(inputBox).not.toBeNull();

  if (!leftBox || !chatBox || !imageBox || !inputBox) {
    return;
  }

  expect(imageBox.height).toBeGreaterThan(minimumImageHeight);
  expect(imageBox.y).toBeGreaterThanOrEqual(leftBox.y);
  expect(imageBox.y + imageBox.height).toBeLessThanOrEqual(
    leftBox.y + leftBox.height + 1,
  );
  expect(leftBox.y + leftBox.height).toBeLessThanOrEqual(chatBox.y + 1);
  expect(inputBox.y + inputBox.height).toBeLessThanOrEqual(
    page.viewportSize()?.height ?? Number.POSITIVE_INFINITY,
  );

  await expect(page.locator(".character-state-panel__image")).toHaveCSS(
    "object-fit",
    "contain",
  );
  await expect
    .poll(() =>
      leftPanel.evaluate(
        (element) => element.scrollHeight > element.clientHeight,
      ),
    )
    .toBe(true);
}

test.describe("モバイルの画像・チャット同時表示", () => {
  test.beforeEach(async ({ page }) => {
    await mockActiveSession(page);
  });

  test("412x915で大きな画像とチャット入力が初期表示内に収まる", async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 412, height: 915 });
    await page.goto(`/play/${sessionId}`);

    await expect(page.locator(".game-play-screen")).toBeVisible();
    await expectImageAndChatVisible(page, 300);

    await page.screenshot({ path: testInfo.outputPath("pixel7-layout.png") });

    const leftPanel = page.locator(".game-play-screen__left-panel");
    const historyStrip = page.locator(".character-state-panel__history-strip");
    await historyStrip.evaluate((element) =>
      element.scrollIntoView({ block: "center" }),
    );
    await expect(historyStrip).toBeInViewport();
    await expect(
      page.locator(".character-state-panel__nav-full"),
    ).toBeInViewport();

    const navigationScrollTop = await leftPanel.evaluate((element) =>
      Math.round(element.scrollTop),
    );
    const navButtons = page.locator(
      ".character-state-panel__nav-full .character-state-panel__nav-btn",
    );

    for (const { buttonIndex, historyIndex } of [
      { buttonIndex: 0, historyIndex: 0 },
      { buttonIndex: 2, historyIndex: 1 },
      { buttonIndex: 2, historyIndex: 2 },
      { buttonIndex: 3, historyIndex: 4 },
    ]) {
      await navButtons.nth(buttonIndex).dispatchEvent("click");
      await expect(
        page.locator(`[data-history-index="${historyIndex}"]`),
      ).toHaveClass(/is-active/);
      await expect
        .poll(async () => {
          const [stripBox, activeBox] = await Promise.all([
            historyStrip.boundingBox(),
            page
              .locator(`[data-history-index="${historyIndex}"]`)
              .boundingBox(),
          ]);
          if (!stripBox || !activeBox) return false;
          return (
            activeBox.x >= stripBox.x &&
            activeBox.x + activeBox.width <= stripBox.x + stripBox.width
          );
        })
        .toBe(true);
      await expect
        .poll(() =>
          leftPanel.evaluate((element) => Math.round(element.scrollTop)),
        )
        .toBe(navigationScrollTop);
    }
  });

  test("375x667でも画像をトリミングせずチャット入力を維持する", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto(`/play/${sessionId}`);

    await expect(page.locator(".game-play-screen")).toBeVisible();
    await expectImageAndChatVisible(page, 200);
  });

  test("412x915でAnlasとNSFWを折りたたんで表示領域を広げる", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 412, height: 915 });
    await page.goto(`/play/${sessionId}`);

    const anlasToggle = page.locator(".game-play-screen__anlas-toggle");
    const anlasContent = page.locator(".game-play-screen__anlas-content");
    const nsfwToggle = page.locator(
      ".character-state-panel__nsfw-section-toggle",
    );
    const nsfwContent = page.locator(".character-state-panel__nsfw-content");
    const screenContent = page.locator(".game-play-screen__content");
    const imageButton = page.locator(".character-state-panel__image-btn");

    await expect(anlasToggle).toBeVisible();
    await expect(nsfwToggle).toBeVisible();
    await expect(anlasToggle).toHaveAttribute("aria-expanded", "false");
    await expect(nsfwToggle).toHaveAttribute("aria-expanded", "false");
    await expect(anlasContent).toBeHidden();
    await expect(nsfwContent).toBeHidden();

    const collapsedScreenHeight = await screenContent.evaluate(
      (element) => element.getBoundingClientRect().height,
    );
    await anlasToggle.click();
    await expect(anlasToggle).toHaveAttribute("aria-expanded", "true");
    await expect(anlasContent).toBeVisible();
    await expect
      .poll(() =>
        screenContent.evaluate(
          (element) => element.getBoundingClientRect().height,
        ),
      )
      .toBeLessThan(collapsedScreenHeight);
    await anlasToggle.click();
    await expect(anlasContent).toBeHidden();

    const collapsedImageHeight = await imageButton.evaluate(
      (element) => element.getBoundingClientRect().height,
    );
    await nsfwToggle.click();
    await expect(nsfwToggle).toHaveAttribute("aria-expanded", "true");
    await expect(nsfwContent).toBeVisible();
    await expect
      .poll(() =>
        imageButton.evaluate(
          (element) => element.getBoundingClientRect().height,
        ),
      )
      .toBeLessThan(collapsedImageHeight);
    await nsfwToggle.click();
    await expect(nsfwContent).toBeHidden();
    await expect(page.locator(".chat-input__textarea")).toBeVisible();
  });

  test("412x915でページ全体に余剰スクロール領域を作らない", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 412, height: 915 });
    await page.goto(`/play/${sessionId}`);

    await expect(page.locator(".game-play-screen")).toBeVisible();

    const viewportMetrics = await page.evaluate(() => {
      const root = document.getElementById("root");
      const app = document.querySelector<HTMLElement>(".app");
      const layout = document.querySelector<HTMLElement>(".main-layout");

      if (!root || !app || !layout) {
        throw new Error("レイアウト要素を取得できませんでした");
      }

      return {
        viewportHeight: window.innerHeight,
        documentClientHeight: document.documentElement.clientHeight,
        documentScrollHeight: document.documentElement.scrollHeight,
        rootHeight: root.getBoundingClientRect().height,
        appHeight: app.getBoundingClientRect().height,
        layoutHeight: layout.getBoundingClientRect().height,
        bodyOverflow: getComputedStyle(document.body).overflow,
      };
    });

    expect(viewportMetrics.documentScrollHeight).toBe(
      viewportMetrics.documentClientHeight,
    );
    expect(viewportMetrics.bodyOverflow).toBe("hidden");

    for (const height of [
      viewportMetrics.rootHeight,
      viewportMetrics.appHeight,
      viewportMetrics.layoutHeight,
    ]) {
      expect(
        Math.abs(height - viewportMetrics.viewportHeight),
      ).toBeLessThanOrEqual(1);
    }

    await page.evaluate(() => window.scrollTo(0, 100));
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
  });

  for (const viewport of [
    { name: "900x800", width: 900, height: 800, direction: "column" },
    { name: "1280x800", width: 1280, height: 800, direction: "row" },
  ] as const) {
    test(`${viewport.name}では既存レイアウトを維持する`, async ({ page }) => {
      await page.setViewportSize({
        width: viewport.width,
        height: viewport.height,
      });
      await page.goto(`/play/${sessionId}`);

      const content = page.locator(".game-play-screen__content");
      const leftPanel = page.locator(".game-play-screen__left-panel");
      const primary = page.locator(".character-state-panel__primary");

      await expect(content).toBeVisible();
      await expect(leftPanel).toBeVisible();
      await expect(page.locator(".chat-input__textarea")).toBeVisible();
      await expect(content).toHaveCSS("flex-direction", viewport.direction);
      await expect(primary).toHaveCSS("display", "contents");
      await expect(
        page.locator(".game-play-screen__anlas-toggle"),
      ).toBeHidden();
      await expect(
        page.locator(".character-state-panel__nsfw-section-toggle"),
      ).toBeHidden();
      await expect(
        page.locator(".game-play-screen__anlas-content"),
      ).toBeVisible();
      await expect(
        page.locator(".character-state-panel__nsfw-content"),
      ).toBeVisible();

      const leftBox = await leftPanel.boundingBox();
      expect(leftBox).not.toBeNull();
      if (!leftBox) return;

      if (viewport.width === 900) {
        expect(leftBox.height).toBeLessThanOrEqual(viewport.height * 0.4 + 1);
      } else {
        expect(leftBox.width).toBe(320);
      }
    });
  }
});
