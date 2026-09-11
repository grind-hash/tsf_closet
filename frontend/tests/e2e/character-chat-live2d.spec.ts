import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, type Page, test } from "@playwright/test";
import type { CharacterChatThread } from "../../src/apis/characterChat";

// Cubism Core は Live2D Proprietary Software License の配布物でリポジトリに含めない。
// 未配置の環境ではこのファイルの検証を飛ばす(配置手順は同ディレクトリの README.md)。
const corePath = fileURLToPath(
  new URL(
    "../../public/live2d/vendor/live2dcubismcore.min.js",
    import.meta.url,
  ),
);
test.skip(
  !existsSync(corePath),
  "Live2D Cubism Core が public/live2d/vendor/ に配置されていません",
);

// 会話入力だけを制御し、Core・moc3・WebGL・音声再生・音量計は実装を通す。
// Core の型定義は持たない(実装側と同じ理由)ため、境界はこの別名に閉じる。
// biome-ignore lint/suspicious/noExplicitAny: 型を持たない外部スクリプトとの境界
type CubismCore = any;

declare global {
  interface Window {
    pilotStreams: ReadableStreamDefaultController<Uint8Array>[];
    pilotSent: unknown[];
    pilotModelCount: number;
    pilotModel: CubismCore | null;
    Live2DCubismCore: CubismCore;
  }
}

test.use({
  channel: "chromium",
  launchOptions: {
    args: [
      "--use-gl=angle",
      "--use-angle=swiftshader-webgl",
      "--enable-webgl",
      "--ignore-gpu-blocklist",
      "--enable-unsafe-swiftshader",
      "--autoplay-policy=no-user-gesture-required",
    ],
  },
});

const modelUrl =
  "/live2d/serena-fullbody-v4/cubism/fullbody-face-rig.model3.json";
const stageSelector = ".character-chat-room__live2d";

function trackModel() {
  window.pilotModelCount = 0;
  const core = window.Live2DCubismCore;
  const original = core.Model.fromMoc;
  core.Model.fromMoc = (moc: CubismCore) => {
    const model = original(moc);
    window.pilotModel = model;
    window.pilotModelCount++;
    const release = model.release.bind(model);
    model.release = () => {
      window.pilotModelCount--;
      release();
    };
    return model;
  };
}

async function parameter(page: Page, id: string) {
  return page.evaluate((id) => {
    const parameters = window.pilotModel?.parameters;
    return parameters?.values[parameters.ids.indexOf(id)] ?? null;
  }, id);
}

async function pixels(page: Page) {
  return page.evaluate(
    () =>
      new Promise<{
        image: string;
        left: number;
        right: number;
        top: number;
        bottom: number;
        width: number;
        height: number;
      }>((resolve) => {
        requestAnimationFrame(() => {
          const canvas = document.querySelector<HTMLCanvasElement>(
            ".character-chat-room__live2d canvas",
          );
          if (!canvas) throw new Error("Live2D の canvas がありません");
          const copy = document.createElement("canvas");
          copy.width = canvas.width;
          copy.height = canvas.height;
          const context = copy.getContext("2d");
          if (!context) throw new Error("画素を検査できません");
          context.drawImage(canvas, 0, 0);
          const { data } = context.getImageData(0, 0, copy.width, copy.height);
          let left = copy.width;
          let right = -1;
          let top = copy.height;
          let bottom = -1;
          for (let y = 0; y < copy.height; y++) {
            for (let x = 0; x < copy.width; x++) {
              if (data[(y * copy.width + x) * 4 + 3] < 16) continue;
              left = Math.min(left, x);
              right = Math.max(right, x);
              top = Math.min(top, y);
              bottom = Math.max(bottom, y);
            }
          }
          resolve({
            image: copy.toDataURL(),
            left,
            right,
            top,
            bottom,
            width: copy.width,
            height: copy.height,
          });
        });
      }),
  );
}

function audioFixture(): string {
  const rate = 16000;
  const samples = rate * 3;
  const data = Buffer.alloc(44 + samples * 2);
  data.write("RIFF", 0);
  data.writeUInt32LE(data.length - 8, 4);
  data.write("WAVEfmt ", 8);
  data.writeUInt32LE(16, 16);
  data.writeUInt16LE(1, 20);
  data.writeUInt16LE(1, 22);
  data.writeUInt32LE(rate, 24);
  data.writeUInt32LE(rate * 2, 28);
  data.writeUInt16LE(2, 32);
  data.writeUInt16LE(16, 34);
  data.write("data", 36);
  data.writeUInt32LE(samples * 2, 40);
  for (let i = 0; i < samples; i++) {
    // 無音 → 有音 → 無音。実際の音量計が反応したことを区別する。
    const value =
      i >= rate * 0.6 && i < rate * 2
        ? Math.sin((i / rate) * 440 * 2 * Math.PI) * 12000
        : 0;
    data.writeInt16LE(Math.round(value), 44 + i * 2);
  }
  return data.toString("base64");
}

async function setup(
  page: Page,
  options: {
    voice?: boolean;
    selected?: boolean;
    kind?: "base" | "session";
    portraitKind?: "scene" | "standing";
  } = {},
) {
  const thread: CharacterChatThread = {
    id: "live2d-base",
    kind: options.kind ?? "base",
    name: "セレナ",
    pronoun: "私",
    portrait_url: "/character-chat/pilot-portrait",
    portrait_missing: false,
    appearance: {
      identity_tags: "silver hair",
      clothing_tags: "purple dress",
      description: "案内役",
      portrait_kind: options.portraitKind ?? "scene",
      source: { type: "base" },
    },
    summary_text: null,
    message_count: 0,
    last_message: null,
    language: "ja",
    nsfw_mode: false,
    created_at: null,
    updated_at: null,
    messages: [],
    avatar: {
      mode: options.selected ? "live2d" : "auto",
      id: null,
      url: options.selected ? modelUrl : null,
      source: "bundled",
      name: "セレナ",
      character_name: null,
      variant_label: null,
      variants: [],
      missing: false,
    },
  };
  const avatarSelections: unknown[] = [];
  const speechRequests: unknown[] = [];
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/live2dcubismcore.min.js", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      body: `${await response.text()}\n(${trackModel.toString()})();`,
    });
  });
  await page.addInitScript(
    ({ voice }) => {
      localStorage.setItem("novelai_api_key_consent", "true");
      localStorage.setItem(
        "app_settings",
        JSON.stringify({
          experimentalCharacterChatEnabled: true,
          fontFamily: "noto-sans-jp",
        }),
      );
      localStorage.setItem("character_chat_info_panel_open", "false");
      localStorage.setItem(
        "adventure_voice_prefs",
        JSON.stringify({ enabled: voice, volume: 0.5, speed: 1 }),
      );
      window.pilotStreams = [];
      window.pilotSent = [];
      const originalFetch = window.fetch.bind(window);
      window.fetch = async (input, init) => {
        if (
          String(input).endsWith(
            "/character-chat/threads/live2d-base/messages/stream",
          )
        ) {
          window.pilotSent.push(JSON.parse(String(init?.body)));
          return new Response(
            new ReadableStream<Uint8Array>({
              start(controller) {
                window.pilotStreams.push(controller);
              },
            }),
            { headers: { "Content-Type": "text/event-stream" } },
          );
        }
        return originalFetch(input, init);
      };
    },
    { voice: options.voice ?? false },
  );
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/avatar") && route.request().method() === "PUT") {
      const selection = route.request().postDataJSON();
      avatarSelections.push(selection);
      if (thread.avatar) {
        thread.avatar.mode = selection.mode;
        thread.avatar.url = selection.mode === "live2d" ? modelUrl : null;
      }
      await route.fulfill({ json: thread });
    } else if (
      path.endsWith("/threads/live2d-base") ||
      path.endsWith("/threads/base")
    ) {
      await route.fulfill({ json: thread });
    } else if (path.endsWith("/threads")) {
      await route.fulfill({ json: { threads: [thread] } });
    } else if (path.endsWith("/pilot-portrait")) {
      await route.fulfill({
        contentType: "image/svg+xml",
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="896" height="1280"><rect width="896" height="1280" fill="#685078"/></svg>',
      });
    } else if (path.endsWith("/settings/user")) {
      await route.fulfill({
        json: { tts_enabled: true, tts_style_id: "1", language: "ja" },
      });
    } else if (path.endsWith("/memory/text")) {
      await route.fulfill({ json: { memory_text: "検証用の記憶" } });
    } else if (path.endsWith("/avatars")) {
      await route.fulfill({ json: { avatars: [] } });
    } else if (path.endsWith("/aivisspeech/status")) {
      await route.fulfill({ json: { process: "running", engine_http: "ok" } });
    } else if (path.endsWith("/synthesize-timed")) {
      speechRequests.push(route.request().postDataJSON());
      await route.fulfill({
        json: {
          audio_base64: audioFixture(),
          content_type: "audio/wav",
          duration_sec: 3,
          timeline: [],
        },
      });
    } else {
      await route.fulfill({ json: {} });
    }
  });
  await page.goto("/talk/live2d-base");
  await expect(page.getByRole("heading", { name: /セレナ/ })).toBeVisible();
  return { thread, avatarSelections, speechRequests, errors };
}

async function select(page: Page, name: string) {
  await page.getByRole("button", { name: "姿", exact: true }).click();
  await page.getByRole("button", { name, exact: false }).click();
}

async function send(page: Page) {
  await page
    .getByRole("textbox", { name: "セレナに話しかける" })
    .fill("一緒にお話ししよう");
  await page.getByRole("button", { name: "送信", exact: true }).click();
  await expect
    .poll(() => page.evaluate(() => window.pilotStreams.length))
    .toBeGreaterThan(0);
}

async function emit(
  page: Page,
  event: string,
  data: unknown,
  close = false,
  index = -1,
) {
  await page.evaluate(
    ({ event, data, close, index }) => {
      const controller = window.pilotStreams.at(index);
      if (!controller) throw new Error("検証用ストリームがありません");
      controller.enqueue(
        new TextEncoder().encode(
          `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`,
        ),
      );
      if (close) controller.close();
    },
    { event, data, close, index },
  );
}

function reply(expression = "happy", turn = 1) {
  return {
    user_message: {
      id: `u${turn}`,
      role: "user",
      content: "一緒にお話ししよう",
      meta: {},
      created_at: null,
    },
    character_message: {
      id: `c${turn}`,
      role: "character",
      content: "お話しできてうれしいです。",
      meta: { expression, gesture: "wave_hand" },
      created_at: null,
    },
    thread: { id: "live2d-base", message_count: turn * 2, updated_at: null },
  };
}

test("案内役の明示選択、実モデル、ストリームと後処理、PC・狭幅、再入場", async ({
  page,
}, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const state = await setup(page);
  await expect(page.locator(stageSelector)).toHaveCount(0);
  await select(page, "Live2D");
  const stage = page.locator(stageSelector);
  await expect(stage).toHaveAttribute("data-ready", "true", { timeout: 20000 });
  expect(state.avatarSelections).toEqual([{ mode: "live2d", avatar_id: null }]);
  await expect(stage.locator("canvas")).toHaveCount(1);
  expect(await page.evaluate(() => window.pilotModel?.parts.count)).toBe(13);
  expect(await page.evaluate(() => window.pilotModel?.drawables.count)).toBe(
    12,
  );
  expect(await page.evaluate(() => window.pilotModelCount)).toBe(1);
  await send(page);
  await expect(stage).toHaveAttribute("data-emotion", "thinking");
  await emit(page, "status", { phase: "reply" });
  await emit(page, "chat_chunk", { chunk: "お話しできて" });
  await expect(page.getByText("お話しできて", { exact: true })).toBeVisible();
  await expect(stage).toHaveAttribute("data-emotion", "thinking");
  await emit(page, "chat_done", reply());
  await expect(stage).toHaveAttribute("data-emotion", "happy");
  await expect
    .poll(() =>
      page.evaluate(() => {
        const drawables = window.pilotModel?.drawables;
        return drawables
          ? drawables.opacities[drawables.ids.indexOf("Expr_Happy")]
          : 0;
      }),
    )
    .toBeGreaterThan(0.95);
  await emit(page, "status", { phase: "memory" });
  await expect(
    page.getByRole("button", { name: "送信", exact: true }),
  ).toBeDisabled();
  await expect(stage).toHaveAttribute("data-emotion", "happy");
  await expect(stage.locator("canvas")).toHaveAttribute("data-mouth", "0.000");
  expect(state.speechRequests).toHaveLength(0);
  await emit(page, "complete", {}, true);
  await expect(
    page.getByRole("button", { name: "全身", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.screenshot({
    path: testInfo.outputPath("live2d-desktop.png"),
    animations: "disabled",
  });
  await page.getByRole("button", { name: "寄り", exact: true }).click();
  await expect(stage).toHaveAttribute("data-camera", "portrait");
  expect(await page.evaluate(() => window.pilotModelCount)).toBe(1);
  await pixels(page);
  await page.screenshot({
    path: testInfo.outputPath("live2d-desktop-portrait.png"),
    animations: "disabled",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(stage).toBeVisible();
  const bounds = await stage.locator("canvas").boundingBox();
  const messageBounds = await page
    .locator(".character-chat-room__messagebox")
    .boundingBox();
  expect(bounds).not.toBeNull();
  expect(messageBounds).not.toBeNull();
  if (bounds && messageBounds)
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(messageBounds.y);
  const topbar = await page
    .locator(".character-chat-room__topbar")
    .boundingBox();
  const controls = await page
    .getByRole("group", { name: "Live2D の表示範囲" })
    .boundingBox();
  if (!topbar || !controls) throw new Error("表示範囲の操作部がありません");
  expect(controls.y).toBeGreaterThan(topbar.y + topbar.height);
  const canvasBounds = await stage.locator("canvas").boundingBox();
  if (!canvasBounds) throw new Error("Live2D の表示領域がありません");
  expect(canvasBounds.y).toBeGreaterThan(controls.y + controls.height);
  await page.screenshot({
    path: testInfo.outputPath("live2d-mobile.png"),
    animations: "disabled",
  });
  await page.getByRole("button", { name: "全身", exact: true }).click();
  await expect(stage).toHaveAttribute("data-camera", "full");
  const mobileFull = await pixels(page);
  expect(mobileFull.top).toBeGreaterThan(0);
  expect(mobileFull.bottom).toBeLessThan(mobileFull.height - 1);
  await page.screenshot({
    path: testInfo.outputPath("live2d-mobile-full.png"),
    animations: "disabled",
  });
  await page.getByRole("button", { name: /一覧へ戻る/ }).click();
  await expect(stage).toHaveCount(0);
  expect(await page.evaluate(() => window.pilotModelCount)).toBe(0);
  await page.getByRole("button", { name: "セレナと話す" }).click();
  await expect(stage).toHaveAttribute("data-ready", "true");
  await expect(stage.locator("canvas")).toHaveCount(1);
  expect(await page.evaluate(() => window.pilotModelCount)).toBe(1);
  await select(page, "2D 立ち絵");
  await expect(stage).toHaveCount(0);
  expect(await page.evaluate(() => window.pilotModelCount)).toBe(0);
  expect(state.errors).toEqual([]);
});

for (const viewport of [
  { width: 1280, height: 720 },
  { width: 390, height: 844 },
]) {
  test(`全身を 2D 立ち絵の大きさにそろえ、ウィンドウを隠して入力を保持する (${viewport.width}px)`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize(viewport);
    await page.emulateMedia({ reducedMotion: "reduce" });
    const state = await setup(page, {
      selected: true,
      portraitKind: "standing",
    });
    const stage = page.locator(stageSelector);
    const canvas = stage.locator("canvas");
    await expect(stage).toHaveAttribute("data-ready", "true");
    const fullBounds = await canvas.boundingBox();
    if (!fullBounds) throw new Error("全身の表示領域がありません");
    await select(page, "2D 立ち絵");
    const portrait = page.locator(".character-chat-room__portrait");
    await expect(portrait).toBeVisible();
    await expect
      .poll(() =>
        portrait.evaluate(
          (element) => (element as HTMLImageElement).naturalWidth,
        ),
      )
      .toBe(896);
    await portrait.evaluate(async (element) => {
      await Promise.all(
        element.getAnimations().map((animation) => animation.finished),
      );
    });
    const portraitBounds = await portrait.boundingBox();
    if (!portraitBounds) throw new Error("立ち絵の表示領域がありません");
    expect(fullBounds.height).toBeCloseTo(portraitBounds.height, 0);
    expect(fullBounds.y + fullBounds.height).toBeCloseTo(
      portraitBounds.y + portraitBounds.height,
      0,
    );
    await select(page, "Live2D");
    await expect(stage).toHaveAttribute("data-ready", "true");
    await pixels(page);
    const actualScale = await canvas.evaluate((element) => {
      const canvas = element as HTMLCanvasElement;
      const gl = canvas.getContext("webgl");
      if (!gl) throw new Error("描画を検査できません");
      const program = gl.getParameter(gl.CURRENT_PROGRAM) as WebGLProgram;
      const location = gl.getUniformLocation(program, "view");
      if (!location) throw new Error("描画範囲を取得できません");
      const view = gl.getUniform(program, location) as Float32Array;
      return canvas.clientHeight / view[3];
    });
    expect(actualScale).toBeCloseTo(
      Math.min(portraitBounds.width / 896, portraitBounds.height / 1280),
      2,
    );
    const input = page.getByRole("textbox", { name: "セレナに話しかける" });
    await input.fill("まだ送らない下書き");
    await page.screenshot({
      path: testInfo.outputPath("matched-fullbody.png"),
      animations: "disabled",
    });
    await page
      .getByRole("button", { name: "ウィンドウを隠す", exact: true })
      .click();
    await expect(input).toBeHidden();
    const show = page.getByRole("button", {
      name: "ウィンドウを表示",
      exact: true,
    });
    await expect(show).toBeVisible();
    await expect(show).toBeFocused();
    await expect(show).toHaveAttribute("aria-expanded", "false");
    expect(await page.evaluate(() => window.pilotModelCount)).toBe(1);
    expect(await canvas.boundingBox()).toEqual(fullBounds);
    await page.screenshot({
      path: testInfo.outputPath("matched-fullbody-window-hidden.png"),
      animations: "disabled",
    });
    await show.press("Enter");
    await expect(input).toBeVisible();
    await expect(input).toHaveValue("まだ送らない下書き");
    expect(await page.evaluate(() => window.pilotSent)).toEqual([]);
    expect(state.speechRequests).toHaveLength(0);
    expect(state.errors).toEqual([]);
  });
}

test("確定返答で読み上げ開始、無音と有音、停止・再読み上げ・OFF・エラー", async ({
  page,
}) => {
  const state = await setup(page, { voice: true, selected: true });
  const stage = page.locator(stageSelector);
  const canvas = stage.locator("canvas");
  await expect(stage).toHaveAttribute("data-ready", "true", { timeout: 20000 });
  await send(page);
  await page
    .getByRole("button", { name: "ウィンドウを隠す", exact: true })
    .click();
  await expect(page.locator(".character-chat-room__messagebox")).toBeHidden();
  await emit(page, "chat_done", reply("sad"));
  await emit(page, "status", { phase: "memory" });
  await expect.poll(() => state.speechRequests.length).toBe(1);
  await expect(stage).toHaveAttribute("data-emotion", "sad");
  await expect(canvas).toHaveAttribute("data-mouth", "0.000");
  await expect
    .poll(async () => Number(await canvas.getAttribute("data-mouth")))
    .toBeGreaterThan(0.3);
  await expect
    .poll(() => parameter(page, "ParamMouthOpenY"))
    .toBeGreaterThan(0.3);
  await expect
    .poll(async () => Number(await canvas.getAttribute("data-mouth")))
    .toBe(0);
  await emit(page, "complete", {}, true);
  await page
    .getByRole("button", { name: "ウィンドウを表示", exact: true })
    .click();
  await expect(
    page.getByText("お話しできてうれしいです。", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "この返答を読み上げ", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
  await page
    .getByRole("button", { name: "この返答を読み上げ", exact: true })
    .click();
  await expect
    .poll(async () => Number(await canvas.getAttribute("data-mouth")))
    .toBeGreaterThan(0.3);
  await page
    .getByRole("button", { name: "この返答を読み上げ", exact: true })
    .click();
  await expect(canvas).toHaveAttribute("data-mouth", "0.000");
  await expect.poll(() => parameter(page, "ParamMouthOpenY")).toBe(0);
  await page
    .getByRole("button", { name: "この返答を読み上げ", exact: true })
    .click();
  await expect
    .poll(async () => Number(await canvas.getAttribute("data-mouth")))
    .toBeGreaterThan(0.3);
  await page.getByRole("button", { name: "サウンド設定" }).click();
  await page.getByText("返答を読み上げる", { exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: /返答を読み上げる/ }),
  ).not.toBeChecked();
  await expect(canvas).toHaveAttribute("data-mouth", "0.000");
  await page.getByText("返答を読み上げる", { exact: true }).click();
  await page.route("**/api/aivisspeech/synthesize-timed", (route) =>
    route.fulfill({ status: 503, json: { detail: "音声エラーの検証" } }),
  );
  await page
    .getByRole("button", { name: "この返答を読み上げ", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "この返答を読み上げ", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
  await expect(canvas).toHaveAttribute("data-mouth", "0.000");
  expect(state.errors).toEqual([]);
});

test("読み込み失敗と通信失敗から復帰し、退室後の遅延返答を再生しない", async ({
  page,
}) => {
  await page.route("**/fullbody-face-rig.moc3", (route) =>
    route.fulfill({ status: 404, body: "" }),
  );
  const state = await setup(page, { voice: true, selected: true });
  await expect(page.getByText(/Live2D を表示できないため/)).toBeVisible();
  await expect(page.locator(".character-chat-room__portrait")).toBeVisible();
  await page.getByRole("alert").getByRole("button", { name: "閉じる" }).click();
  await page.unroute("**/fullbody-face-rig.moc3");
  await select(page, "Live2D");
  const stage = page.locator(stageSelector);
  await expect(stage).toHaveAttribute("data-ready", "true");
  await send(page);
  await emit(page, "error", { message: "通信エラーの検証" }, true);
  await expect(stage).toHaveAttribute("data-emotion", "neutral");
  await expect(
    page.getByRole("textbox", { name: "セレナに話しかける" }),
  ).toBeEnabled();
  await send(page);
  await expect
    .poll(() => page.evaluate(() => window.pilotStreams.length))
    .toBe(2);
  await page.getByRole("button", { name: /一覧へ戻る/ }).click();
  await page.getByRole("button", { name: "セレナと話す" }).click();
  await expect(stage).toHaveAttribute("data-ready", "true");
  await emit(page, "chat_done", reply(), false, 1);
  await emit(page, "complete", {}, true, 1);
  await expect(stage).toHaveAttribute("data-emotion", "neutral");
  expect(state.speechRequests).toHaveLength(0);
  expect(state.errors).toEqual([]);
});

test("セッション由来キャラクターには Live2D 選択を出さない", async ({
  page,
}) => {
  await setup(page, { kind: "session" });
  await page.getByRole("button", { name: "姿", exact: true }).click();
  await expect(page.getByRole("button", { name: /Live2D/ })).toHaveCount(0);
});

test("素材の読み込み途中の切り替えと WebGL の喪失でリソースを解放する", async ({
  page,
}) => {
  let releaseTexture = () => {};
  const textureReady = new Promise<void>((resolve) => {
    releaseTexture = resolve;
  });
  const textureUrl =
    "**/serena-fullbody-v4/cubism/fullbody-face-rig.2048/texture_00.png";
  await page.route(textureUrl, async (route) => {
    const response = await route.fetch();
    await textureReady;
    await route.fulfill({ response });
  });
  const state = await setup(page, { selected: true });
  const stage = page.locator(stageSelector);
  try {
    await expect
      .poll(() => page.evaluate(() => window.pilotModelCount))
      .toBe(1);
    await expect(stage).toHaveAttribute("data-ready", "false");
    await select(page, "2D 立ち絵");
    await expect(stage).toHaveCount(0);
    await expect
      .poll(() => page.evaluate(() => window.pilotModelCount))
      .toBe(0);
  } finally {
    releaseTexture();
  }
  await page.unroute(textureUrl);
  await select(page, "Live2D");
  await expect(stage).toHaveAttribute("data-ready", "true");
  expect(await page.evaluate(() => window.pilotModelCount)).toBe(1);
  await stage.locator("canvas").evaluate((canvas) => {
    const extension = (canvas as HTMLCanvasElement)
      .getContext("webgl")
      ?.getExtension("WEBGL_lose_context");
    if (!extension) throw new Error("WebGL の喪失を再現できません");
    extension.loseContext();
  });
  await expect(page.getByText(/Live2D を表示できないため/)).toBeVisible();
  await expect(page.locator(".character-chat-room__portrait")).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.pilotModelCount)).toBe(0);
  await page.getByRole("alert").getByRole("button", { name: "閉じる" }).click();
  await select(page, "Live2D");
  await expect(stage).toHaveAttribute("data-ready", "true");
  expect(await page.evaluate(() => window.pilotModelCount)).toBe(1);
  expect(state.errors).toEqual([]);
});

test("全身 v4 の画素・表情・接地、モデル内の身体と髪袖の動き、動きを減らす設定", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const state = await setup(page, { selected: true });
  const stage = page.locator(stageSelector);
  await expect(stage).toHaveAttribute("data-ready", "true");
  const full = await pixels(page);
  expect(full.left).toBeGreaterThan(0);
  expect(full.right).toBeGreaterThan(full.left + 30);
  expect(full.right).toBeLessThan(full.width - 1);
  expect(full.top).toBeGreaterThan(0);
  expect(full.bottom).toBeGreaterThan(full.top + 100);
  expect(full.bottom).toBeLessThan(full.height - 1);

  const motionIds = [
    "ParamBreath",
    "ParamBodyAngleZ",
    "ParamHairImageLeft",
    "ParamHairImageRight",
    "ParamSleeveImageLeft",
    "ParamSleeveImageRight",
  ];
  for (const id of motionIds) expect(await parameter(page, id)).toBe(0);
  const baseline = await page.evaluate(() => {
    const m = window.pilotModel;
    if (!m) throw new Error("モデルがありません");
    return {
      positions: m.drawables.vertexPositions.map((v) => Array.from(v)),
      ids: m.drawables.ids,
      originY: m.canvasinfo.CanvasOriginY,
      ppu: m.canvasinfo.PixelsPerUnit,
    };
  });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect.poll(() => parameter(page, "ParamBreath")).toBeGreaterThan(0.01);
  const moving = await page.evaluate((baseline) => {
    const m = window.pilotModel;
    if (!m) throw new Error("モデルがありません");
    const deltas = m.drawables.vertexPositions.map((v, mesh) =>
      Math.max(
        ...Array.from(
          v,
          (value, index) =>
            Math.abs(value - baseline.positions[mesh][index]) * baseline.ppu,
        ),
      ),
    );
    const base = baseline.ids.indexOf("Fullbody_Base");
    let footVertices = 0;
    let footDelta = 0;
    for (let i = 0; i < baseline.positions[base].length; i += 2) {
      const y =
        baseline.originY - baseline.positions[base][i + 1] * baseline.ppu;
      if (y < 1100) continue;
      footVertices++;
      for (const axis of [i, i + 1])
        footDelta = Math.max(
          footDelta,
          Math.abs(
            m.drawables.vertexPositions[base][axis] -
              baseline.positions[base][axis],
          ) * baseline.ppu,
        );
    }
    return { deltas, footDelta, footVertices };
  }, baseline);
  for (const name of [
    "Fullbody_Base",
    "Hair_ImageLeft",
    "Hair_ImageRight",
    "Sleeve_ImageLeft",
    "Sleeve_ImageRight",
  ])
    expect(moving.deltas[baseline.ids.indexOf(name)], name).toBeGreaterThan(
      0.01,
    );
  expect(moving.footVertices).toBe(30);
  expect(moving.footDelta).toBeLessThan(0.002);
  const firstHair = await parameter(page, "ParamHairImageLeft");
  await expect
    .poll(async () =>
      Math.abs(
        ((await parameter(page, "ParamHairImageLeft")) ?? 0) - (firstHair ?? 0),
      ),
    )
    .toBeGreaterThan(0.01);
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const id of motionIds)
    await expect.poll(() => parameter(page, id)).toBe(0);
  expect(
    await stage
      .locator("canvas")
      .evaluate((c) => getComputedStyle(c).transform),
  ).toBe("none");

  await page.getByRole("button", { name: "寄り", exact: true }).click();
  const neutral = await pixels(page);
  expect(neutral.image).not.toBe(full.image);
  expect(neutral.right - neutral.left).toBeGreaterThan(full.right - full.left);
  const faces = new Set([neutral.image]);
  let turn = 0;
  for (const emotion of ["happy", "angry", "sad"]) {
    turn++;
    await send(page);
    await emit(page, "chat_done", reply(emotion, turn));
    await emit(page, "complete", {}, true);
    await expect(stage).toHaveAttribute("data-emotion", emotion);
    const id = `ParamEmotion${emotion[0].toUpperCase()}${emotion.slice(1)}`;
    await expect.poll(() => parameter(page, id)).toBeGreaterThan(0.99);
    faces.add((await pixels(page)).image);
  }
  expect(faces.size).toBe(4);
  await send(page);
  await emit(page, "chat_done", reply("surprised", 4));
  await emit(page, "complete", {}, true);
  await expect(stage).toHaveAttribute("data-emotion", "neutral");
  await expect
    .poll(() => parameter(page, "ParamEmotionSad"))
    .toBeLessThan(0.01);
  await expect
    .poll(() => parameter(page, "ParamEyeLOpen"), {
      timeout: 7000,
      intervals: [30],
    })
    .toBeLessThan(0.8);
  await expect.poll(() => parameter(page, "ParamEyeLOpen")).toBe(1);
  expect(state.speechRequests).toHaveLength(0);
  expect(state.errors).toEqual([]);
});
