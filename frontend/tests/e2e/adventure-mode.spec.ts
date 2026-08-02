import { expect, type Page, test } from "@playwright/test";

const IMAGE = "/mock-scene.png";
const IMAGE_PATH =
  "C:\\source\\tech_study2026\\tsf_closet_base\\backend\\images\\characters\\char1_v2.png";

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
    turns: hasTurn
      ? [
          {
            id: "turn-1",
            turn_number: 1,
            client_turn_id: "client-1",
            user_input: "受付を観察する",
            input_kind: "choice",
            narrative: "受付係の手元に銀色の封蝋が見えた。",
            choices: [
              { id: "a", label: "封蝋について尋ねる" },
              { id: "b", label: "列の後方へ回る" },
              { id: "c", label: "会場へ入る" },
            ],
            image_url: null,
            image_status: "not_requested",
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
    title: "プリンセスにならないと出られない部屋",
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
            title: "プリンセスにならないと出られない部屋",
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
    const request = route.request().postDataJSON() as { preset: string };
    expect(request.preset).toBe("infiltration");
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
        body: `event: status\ndata: {"phase":"judging"}\n\nevent: turn\ndata: ${JSON.stringify(turn)}\n\n`,
      });
    },
  );
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
  await expect(page.getByRole("button", { name: "潜入" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
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
  await expect(page.getByText("銀色の封蝋", { exact: true })).toBeVisible();
  await expect(
    page.getByText("変身後の姿で舞踏会の入口に立っている。"),
  ).toBeVisible();
  await expect(page.getByText("手番 1・選んだ行動")).toBeVisible();
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
    name: /プリンセスにならないと出られない部屋/,
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
      name: /プリンセスにならないと出られない部屋/,
    })
    .click();
  await page.getByRole("button", { name: "シナリオを開始" }).click();

  const overlay = page.locator(".adventure-preparing-overlay");
  await expect(overlay).toHaveAttribute("role", "status");
  await expect(overlay).toContainText("シナリオを準備しています");
  await expect(overlay).toContainText("開始場面の物語と画像を生成中です");
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
  await expect(page.getByRole("status")).toContainText("場面画像を生成中");
  releaseImage?.();
  await expect(page.getByRole("status")).toBeHidden();
});

test("turn submission shows a stage loading indicator while judging", async ({
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
        body: `event: status\ndata: {"phase":"judging"}\n\nevent: complete\ndata: {"status":"complete"}\n\n`,
      });
    },
  );
  await page.goto("/adventure/run-1");

  await page.getByRole("button", { name: "受付を観察する" }).click();
  await expect(page.getByRole("status")).toContainText("次の展開を判定中...");
  await expect(page.locator(".adventure-progress")).toBeHidden();
  releaseTurn?.();
  await expect(page.getByRole("status")).toBeHidden();
});
