import { expect, type Page, test } from "@playwright/test";

const sessionId = "22222222-2222-4222-8222-222222222222";

function createHistory(feelingText = "対応する生成文 2") {
  return [
    {
      id: "paired-history-1",
      instruction: "最初の指示",
      image_url: "/history/images/paired-history-1",
      feeling_text: "対応する生成文 1",
      after_description: "first state",
      timestamp: "2026-08-09T10:00:00+09:00",
      instruction_type: "dress_up",
    },
    {
      id: "paired-history-2",
      instruction: "夜の街で赤いドレスに変える",
      image_url: "/history/images/paired-history-2",
      feeling_text: feelingText,
      after_description: "second state",
      timestamp: "2026-08-09T10:01:00+09:00",
      instruction_type: feelingText ? "dress_up" : "image_only",
    },
  ];
}

async function mockPlaySession(page: Page, initialHistory = createHistory()) {
  let activeHistory = [...initialHistory];

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
      json: { total_anlas: 100, fixed_anlas: 100, purchased_anlas: 0 },
    });
  });
  await page.route("**/api/game/sessions/*/restore", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        session_id: sessionId,
        character_id: "paired-preview-character",
        current_image_url: activeHistory.at(-1)?.image_url,
        transformation_count: 2,
        history: activeHistory,
        stats: { bloom: 10, shame: 20, adaptation: 5, nsfw_mode: false },
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
        '<svg xmlns="http://www.w3.org/2000/svg" width="768" height="1024">',
        '<rect width="768" height="1024" fill="#243b5a"/>',
        '<circle cx="384" cy="300" r="150" fill="#e6a4b4"/>',
        '<rect x="210" y="470" width="348" height="470" rx="120" fill="#8e244d"/>',
        "</svg>",
      ].join(""),
    });
  });
  await page.route("**/api/game/play/stream", async (route) => {
    const requestBody = route.request().postDataJSON() as {
      instruction: string;
      instruction_type: string;
    };
    activeHistory = [
      ...activeHistory,
      {
        id: "image-only-history",
        instruction: requestBody.instruction,
        image_url: "/history/images/image-only-history",
        feeling_text: "",
        after_description: "image-only state",
        timestamp: "2026-08-09T10:02:00+09:00",
        instruction_type: requestBody.instruction_type,
      },
    ];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        "event: image",
        'data: {"image":"aW1hZ2U=","history_id":"image-only-history","seed":42}',
        "",
        "event: complete",
        'data: {"history_id":"image-only-history","transformation_count":2}',
        "",
      ].join("\n"),
    });
  });
}

test("メイン画像プレビューで画像と対応文を左右表示し履歴移動へ追従する", async ({
  page,
}) => {
  await mockPlaySession(page);
  await page.setViewportSize({ width: 1200, height: 800 });
  await page.goto(`/play/${sessionId}`);

  await page.locator(".character-state-panel__image-btn").click();
  const content = page.locator(".image-preview-modal__content--side");
  const image = page.locator(".image-preview-modal__image");
  const caption = page.locator(".image-preview-modal__caption--side");
  await expect(content).toBeVisible();
  await expect(content).toHaveCSS("display", "grid");
  await expect(caption).toContainText("夜の街で赤いドレスに変える");
  await expect(caption).toContainText("対応する生成文 2");

  const [imageBox, captionBox] = await Promise.all([
    image.boundingBox(),
    caption.boundingBox(),
  ]);
  expect(imageBox).not.toBeNull();
  expect(captionBox).not.toBeNull();
  if (imageBox && captionBox) {
    expect(imageBox.x + imageBox.width).toBeLessThanOrEqual(captionBox.x);
  }

  await page.locator(".image-preview-modal__nav--prev").click();
  await expect(caption).toContainText("最初の指示");
  await expect(caption).toContainText("対応する生成文 1");
});

test("モバイルでは上下配置になり空の生成文を明示する", async ({ page }) => {
  await mockPlaySession(page, createHistory(""));
  await page.setViewportSize({ width: 480, height: 800 });
  await page.goto(`/play/${sessionId}`);

  await page.locator(".character-state-panel__image-btn").click();
  const content = page.locator(".image-preview-modal__content--side");
  const image = page.locator(".image-preview-modal__image");
  const caption = page.locator(".image-preview-modal__caption--side");
  await expect(content).toHaveCSS("display", "flex");
  await expect(caption).toContainText("生成テキストはありません");

  const [imageBox, captionBox] = await Promise.all([
    image.boundingBox(),
    caption.boundingBox(),
  ]);
  expect(imageBox).not.toBeNull();
  expect(captionBox).not.toBeNull();
  if (imageBox && captionBox) {
    expect(imageBox.y + imageBox.height).toBeLessThanOrEqual(captionBox.y);
  }
});

test("画像のみ送信はimage_onlyを送り空の応答メッセージを作らない", async ({
  page,
}) => {
  await mockPlaySession(page);
  await page.goto(`/play/${sessionId}`);

  const systemMessages = page.locator(".chat-message--system");
  await expect(
    systemMessages.filter({ hasText: "対応する生成文 2" }),
  ).toBeVisible();
  const initialSystemMessageCount = await systemMessages.count();
  const requestPromise = page.waitForRequest("**/api/game/play/stream");
  await page.locator(".chat-input__type-select").selectOption("image_only");
  await page.locator(".chat-input__textarea").fill("夕焼けの海辺へ移動する");
  await page.locator(".chat-input__send-btn").click();

  const request = await requestPromise;
  expect(request.postDataJSON()).toMatchObject({
    instruction: "夕焼けの海辺へ移動する",
    instruction_type: "image_only",
    transformation_type: "costume",
  });
  await expect
    .poll(() => page.locator(".chat-message--system").count())
    .toBe(initialSystemMessageCount);
  await expect(page.locator(".chat-message--user").last()).toContainText(
    "夕焼けの海辺へ移動する",
  );
});
