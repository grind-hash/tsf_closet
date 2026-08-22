import { fileURLToPath } from "node:url";
import { expect, type Page, test } from "@playwright/test";

const IMAGE = "/mock-scene.png";
// リポジトリ内の実画像を参照する（絶対パス固定だと他環境で ENOENT になる）
const IMAGE_PATH = fileURLToPath(
  new URL("../../../backend/images/characters/char1_v2.png", import.meta.url),
);

function runPayload(turnCount = 0) {
  const hasTurn = turnCount > 0;
  return {
    id: "run-1",
    source_session_id: "session-1",
    source_history_id: null,
    scenario_template_id: null,
    preset: "infiltration",
    title: "潜入ミッション",
    objective: "仮面舞踏会で銀色の封蝋がある招待状の差出人を特定する",
    setting: "企業主催の仮面舞踏会",
    constraints: ["招待状を持っていない", "警備員が顔を確認している"],
    status: "active",
    turn_count: turnCount,
    max_turns: 8,
    remaining_turns: 8 - turnCount,
    ending_title: null,
    ending_summary: null,
    clues: hasTurn ? ["銀色の封蝋"] : [],
    milestones: [
      { id: "gain_access", label: "侵入経路を確保" },
      { id: "secure_target", label: "目的物または情報を確保" },
      { id: "leave_safely", label: "安全に離脱" },
    ],
    completed_milestones: hasTurn ? ["gain_access"] : [],
    opening_narrative: "変身後の姿で舞踏会の入口に立っている。",
    choices: [
      { id: "a", label: "受付を観察する" },
      { id: "b", label: "招待客に話しかける" },
      { id: "c", label: "裏口を探す" },
    ],
    current_image_url: IMAGE,
    current_image_prompt: {
      scene_tags: "masquerade ball entrance, night, chandelier",
      player_tags: "1girl, silver gown, masquerade mask",
      npc_tags: ["receptionist, formal suit"],
    },
    use_precise_reference: false,
    enable_composite_scene: false,
    opening_image_url: IMAGE,
    background_image_url: IMAGE,
    portrait_image_url: IMAGE,
    opening_portrait_url: IMAGE,
    visual_state: {
      location: "舞踏会の入口",
      appearance: "銀髪の令嬢",
      clothing: "銀色のドレス",
      surroundings: "シャンデリアの輝くホール",
      main_characters: [],
    },
    turns: hasTurn
      ? [
          {
            id: "turn-1",
            turn_number: 1,
            client_turn_id: "client-1",
            user_input: "受付を観察する",
            input_kind: "choice",
            narrative: "受付係の手元に銀色の封蝋が見えた。",
            location: "舞踏会の受付",
            choices: [
              { id: "a", label: "封蝋について尋ねる" },
              { id: "b", label: "列の後方へ回る" },
              { id: "c", label: "会場へ入る" },
            ],
            image_url: null,
            image_status: "not_requested",
            portrait_image_url: IMAGE,
            portrait_status: "completed",
            created_at: "2026-08-01T00:00:00",
          },
        ]
      : [],
    created_at: "2026-08-01T00:00:00",
    updated_at: "2026-08-01T00:00:00",
  };
}

function authoredRunPayload(turnCount = 0) {
  return {
    ...runPayload(turnCount),
    scenario_template_id: "princess_locked_room",
    preset: "escape",
    title: "女装してプリンセスにならないと出られない部屋",
    objective:
      "必要な衣装と品物を身につけて扉の採点を100点にし、開いた扉から退出する",
  };
}
async function enableAdventure(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
    window.localStorage.setItem(
      "app_settings",
      JSON.stringify({ experimentalAdventureEnabled: true }),
    );
  });
}

async function mockAdventureApis(
  page: Page,
  savedRuns: ReturnType<typeof runPayload>[] = [],
) {
  const state = {
    createBodies: [] as Record<string, unknown>[],
    setupBodies: [] as Record<string, unknown>[],
  };
  let turnCount = 0;
  let authoredRunCreated = false;
  await page.route("**/api/mock-scene.png", async (route) => {
    await route.fulfill({ path: IMAGE_PATH, contentType: "image/png" });
  });
  await page.route("**/api/gallery/sessions?*", async (route) => {
    await route.fulfill({
      json: {
        sessions: [
          {
            session_id: "session-1",
            character_name: "テストキャラクター",
            thumbnail_url: IMAGE,
            item_count: 1,
            first_timestamp: "2026-08-01T00:00:00",
            last_timestamp: "2026-08-01T00:00:00",
            last_instruction: "赤いドレスを着て街を歩く",
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
        has_more: false,
      },
    });
  });
  await page.route("**/api/gallery?*", async (route) => {
    await route.fulfill({
      json: { items: [], total: 0, page: 1, page_size: 50, has_more: false },
    });
  });
  await page.route("**/api/adventure/templates", async (route) => {
    await route.fulfill({
      json: {
        templates: [
          {
            id: "princess_locked_room",
            preset: "escape",
            title: "女装してプリンセスにならないと出られない部屋",
            synopsis:
              "寒い密室で指定された衣装と品物をそろえ、扉の採点を突破する。",
            setting: "見知らぬ寒い密室",
            objective:
              "必要な衣装と品物を身につけて扉の採点を100点にし、開いた扉から退出する",
            constraints: ["部屋は非常に寒い", "女性用衣類のみ用意されている"],
            max_turns: 8,
            content_rating: "mature",
          },
        ],
      },
    });
  });
  await page.route("**/api/adventure/setup/generate", async (route) => {
    const request = route.request().postDataJSON() as Record<string, unknown>;
    state.setupBodies.push(request);
    // 潜入は選択肢から外れたため、テストは「なりすまし・着替え」で生成する
    expect(request.preset).toBe("disguise");
    await route.fulfill({
      json: {
        setting: "企業主催の仮面舞踏会",
        objective: "仮面舞踏会で銀色の封蝋がある招待状の差出人を特定する",
        constraints: ["招待状を持っていない", "警備員が顔を確認している"],
      },
    });
  });
  await page.route("**/api/adventure/runs", async (route) => {
    if (route.request().method() === "POST") {
      const request = route.request().postDataJSON() as {
        scenario_template_id?: string;
        replay_run_id?: string;
      };
      state.createBodies.push(request as Record<string, unknown>);
      if (request.replay_run_id) {
        expect(request).toMatchObject({
          preset: "infiltration",
          replay_run_id: "saved-run-1",
        });
        await route.fulfill({ status: 201, json: runPayload() });
      } else if (request.scenario_template_id) {
        expect(request).toMatchObject({
          preset: "escape",
          scenario_template_id: "princess_locked_room",
        });
        authoredRunCreated = true;
        await route.fulfill({ status: 201, json: authoredRunPayload() });
      } else {
        expect(request).toMatchObject({
          scenario_setting: "企業主催の仮面舞踏会",
          scenario_objective:
            "仮面舞踏会で銀色の封蝋がある招待状の差出人を特定する",
          scenario_constraints: [
            "招待状を持っていない",
            "警備員が顔を確認している",
          ],
        });
        await route.fulfill({ status: 201, json: runPayload() });
      }
    } else {
      await route.fulfill({ json: { runs: savedRuns } });
    }
  });
  await page.route("**/api/adventure/runs/run-1", async (route) => {
    await route.fulfill({
      json: authoredRunCreated
        ? authoredRunPayload(turnCount)
        : runPayload(turnCount),
    });
  });
  await page.route(
    "**/api/adventure/runs/run-1/turns/stream",
    async (route) => {
      turnCount = 1;
      const turn = {
        ...runPayload(1).turns[0],
        run_status: "active",
        remaining_turns: 7,
        clues: ["銀色の封蝋"],
      };
      await route.fulfill({
        contentType: "text/event-stream",
        body: `event: status\ndata: {"phase":"narrative"}\n\nevent: narrative_chunk\ndata: {"text":"受付係の手元に銀色の封蜡が見えた。"}\n\nevent: narrative_done\ndata: {"narrative":"受付係の手元に銀色の封蜡が見えた。"}\n\nevent: status\ndata: {"phase":"clue_check"}\n\nevent: status\ndata: {"phase":"image_generation","step":"portrait","step_index":1,"step_count":2}\n\nevent: status\ndata: {"phase":"image_generation","step":"composite","step_index":2,"step_count":2}\n\nevent: turn\ndata: ${JSON.stringify(turn)}\n\nevent: complete\ndata: {"status":"complete"}\n\n`,
      });
    },
  );
  return state;
}

test("experimental setting hides adventure route by default", async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
  });
  await page.goto("/adventure");
  await expect(page).toHaveURL(/\/play\/new$/);
});

test("create and play an adventure from a session state", async ({ page }) => {
  await enableAdventure(page);
  await mockAdventureApis(page);
  await page.goto("/adventure");

  await expect(
    page.getByRole("heading", { name: "TSFシナリオ" }),
  ).toBeVisible();
  // 既定ミッションは恋愛シミュレーション(潜入は非表示)
  await expect(
    page.getByRole("button", { name: /^恋愛シミュレーション/ }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: /^なりすまし・着替え/ }).click();
  await expect(
    page.getByRole("button", { name: "シナリオを開始" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "ミッション案を自動生成" }).click();
  await expect(page.getByLabel("舞台")).toHaveValue("企業主催の仮面舞踏会");
  await expect(page.getByLabel("ゴール")).toHaveValue(
    "仮面舞踏会で銀色の封蝋がある招待状の差出人を特定する",
  );
  await expect(page.getByLabel("制約")).toHaveValue(
    "招待状を持っていない\n警備員が顔を確認している",
  );
  await page.getByRole("button", { name: "シナリオを開始" }).click();

  await expect(page).toHaveURL(/\/adventure\/run-1$/);
  await expect(page.getByRole("heading", { name: /仮面舞踏会/ })).toBeVisible();
  await expect(
    page.getByText("変身後の姿で舞踏会の入口に立っている。"),
  ).toBeVisible();
  await page.getByRole("button", { name: "受付を観察する" }).click();
  await expect(
    page.getByText("受付係の手元に銀色の封蝋が見えた。"),
  ).toBeVisible();
  await expect(page.getByText("舞踏会の受付")).toBeVisible();

  await page.getByRole("button", { name: "ログ", exact: true }).click();
  const logPanel = page.getByRole("dialog", { name: "これまでの物語" });
  await expect(logPanel).toContainText(
    "変身後の姿で舞踏会の入口に立っている。",
  );
  await expect(logPanel).toContainText("手番 1・選んだ行動");
  await page.getByRole("button", { name: "ログを閉じる" }).first().click();
  await expect(logPanel).toBeHidden();

  await page.getByRole("button", { name: /^手掛かり/ }).click();
  const cluePanel = page.getByRole("dialog", { name: "手掛かり" });
  await expect(
    cluePanel.getByText("銀色の封蝋", { exact: true }),
  ).toBeVisible();
});

test("create an adventure starting from a favorite", async ({ page }) => {
  await enableAdventure(page);
  const state = await mockAdventureApis(page);
  await page.route("**/api/favorites?*", async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            id: "fav-1",
            history_id: "h9",
            session_id: "session-1",
            label: "お気に入りの魔法少女",
            image_url: IMAGE,
            instruction: "魔法少女に変身",
            costume_category: null,
            history_created_at: "2026-08-01T00:00:00",
            created_at: "2026-08-02T00:00:00",
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        has_more: false,
      },
    });
  });
  await page.goto("/adventure");

  // 先頭セッションが自動選択され、サマリに表示される
  const sourceCard = page.locator(".adventure-card--source");
  await expect(sourceCard.getByRole("group")).toContainText(
    "テストキャラクター",
  );
  // 選択モーダルのお気に入りタブから1クリックでセッションと時点を同時決定する
  await sourceCard.getByRole("button", { name: "変更" }).click();
  const picker = page.getByRole("dialog", { name: "開始セッション" });
  await picker.getByRole("tab", { name: "お気に入り" }).click();
  await picker.getByRole("button", { name: "お気に入りの魔法少女" }).click();
  await expect(picker).toBeHidden();
  await expect(sourceCard.getByRole("group")).toContainText(
    "お気に入りの魔法少女",
  );

  await page.getByRole("button", { name: /^なりすまし・着替え/ }).click();
  await page.getByRole("button", { name: "ミッション案を自動生成" }).click();
  await page.getByRole("button", { name: "シナリオを開始" }).click();

  await expect(page).toHaveURL(/\/adventure\/run-1$/);
  expect(state.createBodies[0]).toMatchObject({
    source_session_id: "session-1",
    source_history_id: "h9",
  });
});

test("create an adventure from an authored scenario", async ({ page }) => {
  await enableAdventure(page);
  await mockAdventureApis(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/adventure");

  await page.getByRole("button", { name: "シナリオを選ぶ" }).click();
  const dialog = page.getByRole("dialog", { name: "シナリオを選ぶ" });
  const tabs = dialog.getByRole("tab");
  await expect(tabs).toHaveCount(2);
  expect(await tabs.allTextContents()).toEqual([
    "プレイしたシナリオ",
    "作品シナリオ",
  ]);
  const authoredBounds = await dialog.boundingBox();
  await dialog.getByRole("tab", { name: "プレイしたシナリオ" }).click();
  await expect(dialog).toContainText("プレイしたシナリオはまだありません");
  const playedBounds = await dialog.boundingBox();
  expect(
    Math.abs((playedBounds?.width ?? 0) - (authoredBounds?.width ?? 0)),
  ).toBeLessThanOrEqual(1);
  expect(
    Math.abs((playedBounds?.height ?? 0) - (authoredBounds?.height ?? 0)),
  ).toBeLessThanOrEqual(1);
  await dialog.getByRole("tab", { name: "作品シナリオ" }).click();
  const scenario = page.getByRole("button", {
    name: /女装してプリンセスにならないと出られない部屋/,
  });
  await expect(scenario).toBeVisible();
  await expect(
    scenario.getByText(
      "必要な衣装と品物を身につけて扉の採点を100点にし、開いた扉から退出する",
    ),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/adventure-scenario-modal-mobile.png",
    fullPage: true,
  });
  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
  await scenario.click();
  await page.getByRole("button", { name: "シナリオを開始" }).click();

  await expect(page).toHaveURL(/\/adventure\/run-1$/);
  await expect(
    page.getByRole("heading", {
      name: /必要な衣装と品物を身につけて扉の採点を100点/,
    }),
  ).toBeVisible();
});

test("reuse a played scenario as a new run", async ({ page }) => {
  await enableAdventure(page);
  const playedRun = {
    ...runPayload(3),
    id: "saved-run-1",
    title: "以前の潜入ミッション",
  };
  await mockAdventureApis(page, [playedRun]);
  await page.goto("/adventure");

  await page.getByRole("button", { name: "シナリオを選ぶ" }).click();
  const dialog = page.getByRole("dialog", { name: "シナリオを選ぶ" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("tab", { name: "プレイしたシナリオ" }).click();
  await dialog.getByRole("button", { name: /以前の潜入ミッション/ }).click();

  await expect(
    page
      .locator(".adventure-selected-scenario")
      .getByText("以前の潜入ミッション"),
  ).toBeVisible();
  await page.getByRole("button", { name: "シナリオを開始" }).click();
  await expect(page).toHaveURL(/\/adventure\/run-1$/);
});
test("scenario creation shows a full-screen loading overlay", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockAdventureApis(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/adventure");

  let releaseCreate: (() => void) | undefined;
  await page.route("**/api/adventure/runs", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    await new Promise<void>((resolve) => {
      releaseCreate = resolve;
    });
    await route.fulfill({ status: 201, json: authoredRunPayload() });
  });

  await page.getByRole("button", { name: "シナリオを選ぶ" }).click();
  await page
    .getByRole("button", {
      name: /女装してプリンセスにならないと出られない部屋/,
    })
    .click();
  await page.getByRole("button", { name: "シナリオを開始" }).click();

  const overlay = page.locator(".adventure-preparing-overlay");
  await expect(overlay).toHaveAttribute("role", "status");
  await expect(overlay).toContainText("シナリオを準備しています");
  await expect(overlay).toContainText("開始場面の物語と画像を生成中です");
  await expect(overlay).toContainText("2分以上かかる場合があります");
  const bounds = await overlay.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds?.x).toBeLessThanOrEqual(1);
  expect(bounds?.y).toBeLessThanOrEqual(1);
  expect(bounds?.width).toBeGreaterThanOrEqual(389);
  expect(bounds?.height).toBeGreaterThanOrEqual(843);

  await expect.poll(() => Boolean(releaseCreate)).toBe(true);
  releaseCreate?.();
  await expect(page).toHaveURL(/\/adventure\/run-1$/);
});
test("play screen fits a mobile viewport without horizontal overflow", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockAdventureApis(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/adventure/run-1");
  await expect(page.locator(".adventure-play")).toBeVisible();
  await page.locator(".adventure-stage__image-button").click();
  const previewContent = page.locator(".image-preview-modal__content");
  await expect(previewContent).toBeVisible();
  // 場面詳細ビューなので常にサイドキャプション（狭い画面では縦積みにフォールバック）
  await expect(previewContent).toHaveClass(
    /image-preview-modal__content--side/,
  );
  await expect(
    page.locator(".image-preview-modal__caption--side"),
  ).toBeVisible();
  await expect(previewContent).toContainText("物語");
  await expect(page.getByRole("button", { name: "シーン" })).toBeVisible();
  await page.getByRole("button", { name: "閉じる" }).click();
  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({
    path: "test-results/adventure-mobile.png",
    fullPage: true,
  });
});

test("narration keeps room next to the action panel", async ({ page }) => {
  await enableAdventure(page);
  await mockAdventureApis(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/adventure/run-1");
  await expect(page.locator(".adventure-messagebox")).toBeVisible();

  const text = page.locator(".adventure-messagebox__text");
  const box = await text.boundingBox();
  expect(box?.height ?? 0).toBeGreaterThan(160);
  const clipped = await text.evaluate(
    (el) => el.scrollHeight - el.clientHeight,
  );
  expect(clipped).toBeLessThanOrEqual(1);

  // 自由入力はトグルの奥ではなく常設
  await expect(
    page.getByRole("textbox", { name: "行動や会話を自由に入力" }),
  ).toBeVisible();

  await page.screenshot({ path: "test-results/adventure-desktop.png" });
});

test("scene detail modal navigates without moving the stage", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockAdventureApis(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/adventure/run-1");
  // 手番を1つ進めてフレームを2枚にする
  await page.getByRole("button", { name: "受付を観察する" }).click();
  await expect(page.locator(".adventure-messagebox__action")).toContainText(
    "受付を観察する",
  );

  await page.locator(".adventure-stage__image-button").click();
  const previewContent = page.locator(".image-preview-modal__content");
  await expect(previewContent).toBeVisible();
  await expect(previewContent).toContainText("手番");
  await expect(previewContent).toContainText("1 / 8");
  await expect(previewContent).toContainText("選んだ行動");
  await expect(page.getByRole("button", { name: "背景" })).toBeVisible();
  // 出現アニメーション（0.2s）の完了を待ってから撮る
  await page.waitForTimeout(400);
  await page.screenshot({ path: "test-results/adventure-scene-modal.png" });

  // ‹ で開始場面へ戻ってもステージ側は最新のまま
  await page.getByRole("button", { name: "前の画像" }).click();
  await expect(previewContent).toContainText("開始");
  await expect(page.locator(".adventure-stage__past-banner")).toBeHidden();
  await page.getByRole("button", { name: "閉じる" }).click();
  await expect(page.locator(".adventure-stage__past-banner")).toBeHidden();
});

test("play screen fits a short landscape viewport", async ({ page }) => {
  await enableAdventure(page);
  await mockAdventureApis(page);
  await page.setViewportSize({ width: 740, height: 420 });
  await page.goto("/adventure/run-1");
  await expect(page.locator(".adventure-play")).toBeVisible();
  await expect(page.locator(".adventure-messagebox")).toBeVisible();
  await expect(page.getByRole("button", { name: /^1/ })).toBeVisible();

  const overflow = await page.evaluate(() => ({
    x:
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
    y:
      document.documentElement.scrollHeight -
      document.documentElement.clientHeight,
  }));
  expect(overflow.x).toBeLessThanOrEqual(1);
  expect(overflow.y).toBeLessThanOrEqual(1);
  await page.screenshot({ path: "test-results/adventure-landscape.png" });
});

test("saved adventures remain reachable in a short mobile viewport", async ({
  page,
}) => {
  await enableAdventure(page);
  const savedRuns = Array.from({ length: 8 }, (_, index) => ({
    ...runPayload(),
    id: `saved-run-${index + 1}`,
    title: `保存シナリオ ${index + 1}`,
  }));
  await mockAdventureApis(page, savedRuns);
  await page.setViewportSize({ width: 390, height: 640 });
  await page.goto("/adventure");

  const hub = page.locator(".adventure-hub");
  const dimensions = await hub.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
  }));
  expect(dimensions.scrollHeight).toBeGreaterThan(dimensions.clientHeight);

  const lastRun = page.getByText("保存シナリオ 8", { exact: true });
  await lastRun.scrollIntoViewIfNeeded();
  await expect(lastRun).toBeVisible();
});

test("generate setup sends the typed draft fields", async ({ page }) => {
  await enableAdventure(page);
  const state = await mockAdventureApis(page);
  await page.goto("/adventure");
  await page.getByRole("button", { name: /^なりすまし・着替え/ }).click();
  // 折りたたみを開いてから下書きを入力する
  await page.getByText("舞台・ゴール・制約を直接入力する").click();
  await page.getByLabel("舞台").fill("夜の港町");
  await page.getByLabel("制約").fill("警備が厳しい\n\n身分証を持っていない");
  await page.getByRole("button", { name: "ミッション案を自動生成" }).click();
  await expect(page.getByLabel("舞台")).toHaveValue("企業主催の仮面舞踏会");

  expect(state.setupBodies).toHaveLength(1);
  expect(state.setupBodies[0]).toMatchObject({
    scenario_setting: "夜の港町",
    scenario_constraints: ["警備が厳しい", "身分証を持っていない"],
  });
  // 空欄の項目はキー自体を送らない
  expect(state.setupBodies[0]).not.toHaveProperty("scenario_objective");
});

test("hub offers to resume the last played run above the setup", async ({
  page,
}) => {
  await enableAdventure(page);
  await page.addInitScript(() => {
    window.localStorage.setItem("adventure_last_run_id", "run-1");
  });
  await mockAdventureApis(page, [runPayload()]);
  await page.goto("/adventure");

  const banner = page.locator(".adventure-continue");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("中断したシナリオを再開");
  await expect(banner).toContainText(runPayload().title);
  // バナーは削除ボタンを持たない
  await expect(banner.getByRole("button", { name: "削除" })).toHaveCount(0);
  // サイドメニューにも直前のシナリオへの導線が出る
  await expect(
    page.getByRole("button", { name: "直前のシナリオへ" }),
  ).toBeVisible();

  await banner.getByRole("button", { name: "再開" }).click();
  await expect(page).toHaveURL(/\/adventure\/run-1$/);
});

test("hub hides the resume banner when the last run is finished", async ({
  page,
}) => {
  await enableAdventure(page);
  await page.addInitScript(() => {
    window.localStorage.setItem("adventure_last_run_id", "run-1");
  });
  await mockAdventureApis(page, [{ ...runPayload(), status: "success" }]);
  await page.goto("/adventure");

  await expect(
    page.getByRole("heading", { name: "TSFシナリオ" }),
  ).toBeVisible();
  await expect(page.locator(".adventure-continue")).toHaveCount(0);
});

test("manual image regeneration shows a stage loading indicator", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockAdventureApis(page);
  let releaseImage: (() => void) | undefined;
  await page.route(
    "**/api/adventure/runs/run-1/image/stream",
    async (route) => {
      await new Promise<void>((resolve) => {
        releaseImage = resolve;
      });
      await route.fulfill({
        contentType: "text/event-stream",
        body: `event: status\ndata: {"phase":"image_generation"}\n\nevent: image\ndata: {"image_url":"/mock-scene.png"}\n\nevent: complete\ndata: {"status":"complete"}\n\n`,
      });
    },
  );
  await page.goto("/adventure/run-1");

  await page.getByRole("button", { name: "現在の場面画像を再生成" }).click();
  await expect(page.getByLabel("場面（背景・構図・照明）")).toHaveValue(
    "masquerade ball entrance, night, chandelier",
  );
  await page.getByRole("button", { name: "この内容で再生成" }).click();
  await expect(page.getByRole("status")).toContainText("場面画像を生成中");
  releaseImage?.();
  await expect(page.getByRole("status")).toBeHidden();
});

test("turn submission streams the narrative before the clue check", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockAdventureApis(page);
  let releaseTurn: (() => void) | undefined;
  await page.route(
    "**/api/adventure/runs/run-1/turns/stream",
    async (route) => {
      await new Promise<void>((resolve) => {
        releaseTurn = resolve;
      });
      await route.fulfill({
        contentType: "text/event-stream",
        body: `event: status\ndata: {"phase":"clue_check"}\n\nevent: complete\ndata: {"status":"complete"}\n\n`,
      });
    },
  );
  await page.goto("/adventure/run-1");

  await page.getByRole("button", { name: "受付を観察する" }).click();
  await expect(page.getByRole("status")).toContainText("物語を生成中...");
  await expect(page.locator(".adventure-progress")).toBeHidden();
  // 生成中は前ターンの選択肢を無効表示で残さず、丸ごと隠す
  await expect(page.locator(".adventure-choices")).toHaveCount(0);
  releaseTurn?.();
  await expect(page.getByRole("status")).toBeHidden();
  await expect(page.locator(".adventure-choices")).toBeVisible();
});

test("setup shows a turn time estimate that follows the toggles", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockAdventureApis(page);
  await page.goto("/adventure");

  // 既定ミッションは romance のため、攻略対象立ち絵を含まない preset に切り替える
  await page.getByRole("button", { name: /^なりすまし・着替え/ }).click();
  await page.getByText("生成オプション", { exact: true }).click();
  const textOnlyNotice = page.getByText(
    "※現在の設定では、テキスト生成のみで背景やキャラクターの画像は変更されません。",
  );
  // 既定(非合成・主人公立ち絵を毎ターン描く)は 18秒+ベース20秒 → 約40秒
  await expect(page.getByText("1ターンの生成時間: 約40秒")).toBeVisible();
  await expect(textOnlyNotice).toBeHidden();
  // 立ち絵の毎ターン描画をOFFにすると画像生成なしの約20秒
  const portraitToggle = page.locator("label.adventure-precise-toggle", {
    hasText: "主人公の立ち絵を毎ターン描く",
  });
  await portraitToggle.click();
  await expect(page.getByText("1ターンの生成時間: 約20秒")).toBeVisible();
  await expect(textOnlyNotice).toBeVisible();
  // 合成ONは立ち絵OFFのままでも合成シーンを描くため、告知は消えて20秒ぶん伸びる
  await page
    .locator("label.adventure-precise-toggle", {
      hasText: "背景と人物を同時に描く",
    })
    .click();
  await expect(page.getByText("1ターンの生成時間: 約40秒")).toBeVisible();
  await expect(textOnlyNotice).toBeHidden();
  // 合成ONでも立ち絵トグルは操作でき、ONに戻すと立ち絵の18秒が加算される
  await expect(portraitToggle).toBeVisible();
  await portraitToggle.click();
  await expect(page.getByText("1ターンの生成時間: 約60秒")).toBeVisible();
});

test("declared reality rules are surfaced in the HUD", async ({ page }) => {
  const RULE = "僕のあらゆる行動は、あらゆる人に疑問に思われなくなる";
  await enableAdventure(page);
  await mockAdventureApis(page);
  await page.route("**/api/adventure/runs/run-1", async (route) => {
    await route.fulfill({ json: { ...runPayload(1), reality_rules: [RULE] } });
  });
  await page.goto("/adventure/run-1");

  const chip = page.getByRole("button", { name: /現実改変/ });
  await expect(chip).toBeVisible();
  await chip.click();
  const popover = page.getByRole("dialog", { name: "現実改変" });
  await expect(popover).toContainText(RULE);
  await expect(popover).toContainText("以降のすべての判定に適用");

  // romance 以外でも同じ管理UIへ入れる(ボタン名に「現実改変」は入れない。
  // HUDチップと名前が衝突して strict mode 違反になるため)
  await popover.getByRole("button", { name: "ルールを管理" }).click();
  const manager = page.getByRole("dialog", { name: "現実改変ルールを管理" });
  await expect(manager.getByText(RULE, { exact: true })).toBeVisible();
});

test("bgm chip surfaces the selection reason in the HUD popover", async ({
  page,
}) => {
  const REASON = "受付での緊張感のある駆け引きが続くため";
  await enableAdventure(page);
  await mockAdventureApis(page);
  await page.route("**/api/adventure/runs/run-1", async (route) => {
    const base = runPayload(1);
    await route.fulfill({
      json: {
        ...base,
        opening_bgm: "daily",
        opening_bgm_reason: "開幕は日常的な場面のため",
        bgm: "dark",
        bgm_reason: REASON,
        turns: base.turns.map((turn) => ({
          ...turn,
          bgm: "dark",
          bgm_reason: REASON,
        })),
      },
    });
  });
  await page.goto("/adventure/run-1");

  const chip = page.getByRole("button", { name: "dark", exact: true });
  await expect(chip).toBeVisible();
  await chip.click();
  const popover = page.getByRole("dialog", { name: "BGM" });
  await expect(popover).toContainText("dark");
  await expect(popover).toContainText("選曲理由");
  await expect(popover).toContainText(REASON);
});

test("finished run shows the result overlay", async ({ page }) => {
  await enableAdventure(page);
  await mockAdventureApis(page);
  await page.route("**/api/adventure/runs/run-1", async (route) => {
    await route.fulfill({
      json: {
        ...runPayload(1),
        status: "success",
        turn_count: 3,
        remaining_turns: 0,
        ending_title: "封蝋の主",
        ending_summary: "差出人の正体を掴み、静かに会場を後にした。",
        completed_milestones: ["gain_access", "secure_target", "leave_safely"],
        choices: [],
      },
    });
  });
  await page.goto("/adventure/run-1");

  const result = page.getByRole("dialog", { name: "封蝋の主" });
  await expect(result).toBeVisible();
  await expect(result).toContainText("成功");
  await expect(result).toContainText(
    "差出人の正体を掴み、静かに会場を後にした。",
  );
  await expect(result).toContainText("到達手番");
  await expect(result).toContainText("安全に離脱");

  await page.getByRole("button", { name: "ログを読む" }).click();
  await expect(result).toBeHidden();
  await expect(
    page.getByRole("dialog", { name: "これまでの物語" }),
  ).toBeVisible();
});

test("too many constraints block start and generation with a reason", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockAdventureApis(page);
  await page.goto("/adventure");
  await page.getByRole("button", { name: /^なりすまし・着替え/ }).click();
  await page.getByText("舞台・ゴール・制約を直接入力する").click();
  await page.getByLabel("ゴール").fill("仮面舞踏会で招待状の差出人を特定する");
  const lines = Array.from({ length: 21 }, (_, index) => `制約${index + 1}`);
  await page.getByLabel("制約").fill(lines.join("\n"));

  // 理由は入力欄のヒントと開始ボタンの status の両方に出る
  await expect(
    page.locator(".adventure-setup-constraints__hint--over"),
  ).toHaveText("制約は最大20件です（現在21件）");
  await expect(page.getByRole("status")).toHaveText(
    "制約は最大20件です（現在21件）",
  );
  await expect(
    page.getByRole("button", { name: "シナリオを開始" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "ミッション案を自動生成" }),
  ).toBeDisabled();

  // 上限内に減らせば再び開始できる
  await page.getByLabel("制約").fill(lines.slice(0, 20).join("\n"));
  await expect(page.getByText("制約 20/20件")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "シナリオを開始" }),
  ).toBeEnabled();
});
