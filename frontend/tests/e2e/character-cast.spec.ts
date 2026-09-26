/**
 * 複数人表示の登場人物（設定モーダル・登場 ON/OFF・組み合わせ）のモック済み E2E。
 * バックエンド無しで、人物パネルとモーダルの振る舞いと送信内容を確認する。
 */
import { expect, type Page, test } from "@playwright/test";

const sessionId = "55555555-5555-4555-8555-555555555555";

interface MockCharacter {
  id: string;
  session_id: string;
  slot_index: number;
  name: string;
  appearance_natural: string;
  appearance_tags: string;
  position: string;
  is_protagonist: boolean;
  appearance_lock: boolean;
  exclude_from_effects: boolean;
  source_preset_id: string | null;
  negative_tags: string;
  profile: Record<string, unknown> | null;
  on_stage: boolean;
  thumbnail_url: string | null;
  created_at: string;
  updated_at: string;
}

function makeCharacter(
  id: string,
  slotIndex: number,
  overrides: Partial<MockCharacter> = {},
): MockCharacter {
  return {
    id,
    session_id: sessionId,
    slot_index: slotIndex,
    name: id,
    appearance_natural: "",
    appearance_tags: "",
    position: "center",
    is_protagonist: false,
    appearance_lock: false,
    exclude_from_effects: false,
    source_preset_id: null,
    negative_tags: "",
    profile: null,
    on_stage: true,
    thumbnail_url: null,
    created_at: "2026-09-26T10:00:00",
    updated_at: "2026-09-26T10:00:00",
    ...overrides,
  };
}

interface MockState {
  characters: MockCharacter[];
  groups: Array<{
    id: string;
    name: string;
    members: Array<Record<string, unknown>>;
    created_at: string;
    updated_at: string;
  }>;
  updates: Array<{ id: string; body: Record<string, unknown> }>;
  profileRequests: Array<Record<string, unknown>>;
  resolveRequests: Array<Record<string, unknown>>;
  groupCreates: Array<Record<string, unknown>>;
}

async function mockCastSession(
  page: Page,
  characters: MockCharacter[],
): Promise<MockState> {
  const state: MockState = {
    characters,
    groups: [],
    updates: [],
    profileRequests: [],
    resolveRequests: [],
    groupCreates: [],
  };
  await page.addInitScript(() => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
    window.localStorage.setItem("novelai_opus_confirmed", "true");
    window.localStorage.setItem(
      "app_settings",
      JSON.stringify({
        enableMultiplePeople: true,
        multiCharacterPanelEnabled: true,
      }),
    );
  });
  // 個別に定義しない API は空で返す（後から登録したルートが優先される）
  await page.route("**/api/**", async (route) => {
    await route.fulfill({ status: 200, json: {} });
  });
  await page.route("**/health", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        status: "ok",
        image_provider: "novelai",
        image_description_provider: "novelai",
        feeling_provider: "novelai",
      },
    });
  });
  await page.route("**/api/settings/user", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        nsfw_mode: false,
        difficulty: "normal",
        language: "ja",
        novelai_image_model: "nai-diffusion-4-5-full",
        novelai_curated_image_model: "nai-diffusion-4-5-curated",
        tts_enabled: false,
      },
    });
  });
  await page.route("**/api/game/characters", async (route) => {
    await route.fulfill({ status: 200, json: { characters: [] } });
  });
  await page.route("**/api/game/anlas", async (route) => {
    await route.fulfill({
      status: 200,
      json: { total_anlas: 120, fixed_anlas: 100, purchased_anlas: 20 },
    });
  });
  await page.route("**/api/game/sessions/*/play-memory", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        system_enabled: false,
        user_enabled: false,
        system_text: "",
        user_text: "",
        system_updated_at: null,
      },
    });
  });
  await page.route("**/api/history/images/*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="#345"/></svg>',
    });
  });
  const sessionPayload = {
    session_id: sessionId,
    character_id: "mock-character",
    current_image_url: "/history/images/hist-1",
    transformation_count: 1,
    history: [
      {
        id: "hist-1",
        instruction: "制服に着替える",
        image_url: "/history/images/hist-1",
        feeling_text: "心境",
        after_description: "1boy",
        timestamp: "2026-09-26T10:00:00+09:00",
        instruction_type: "dress_up",
      },
    ],
    stats: { bloom: 10, shame: 50, adaptation: 0, nsfw_mode: false },
    attributes: [],
    conversation_history: [],
  };
  await page.route("**/api/game/session", async (route) => {
    await route.fulfill({ status: 200, json: sessionPayload });
  });
  await page.route("**/api/game/sessions/*/restore", async (route) => {
    await route.fulfill({ status: 200, json: sessionPayload });
  });
  await page.route("**/api/gallery/sessions?*", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        sessions: [
          {
            session_id: "source-session",
            character_name: "ミオ",
            thumbnail_url: "/history/images/source-1",
            item_count: 3,
            first_timestamp: "2026-09-20T10:00:00",
            last_timestamp: "2026-09-20T11:00:00",
            last_instruction: "ツインテールにする",
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        has_more: false,
      },
    });
  });

  const listResponse = () => ({ characters: state.characters });
  await page.route(
    `**/api/game/session/${sessionId}/characters**`,
    async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const rest = url.pathname.split("/characters")[1] ?? "";
      const method = request.method();
      if (rest === "" && method === "GET") {
        await route.fulfill({ status: 200, json: listResponse() });
        return;
      }
      if (rest === "/ensure-protagonist") {
        await route.fulfill({ status: 200, json: listResponse() });
        return;
      }
      if (rest === "" && method === "POST") {
        const body = request.postDataJSON() as Record<string, unknown>;
        const created = makeCharacter(
          `char-${state.characters.length + 1}`,
          state.characters.length,
          body as Partial<MockCharacter>,
        );
        state.characters.push(created);
        await route.fulfill({ status: 201, json: created });
        return;
      }
      if (rest.startsWith("/from-group/")) {
        const groupId = rest.split("/").pop() ?? "";
        const group = state.groups.find((g) => g.id === groupId);
        const protagonist = state.characters.filter((c) => c.is_protagonist);
        state.characters = [
          ...protagonist,
          ...(group?.members ?? []).map((member, index) =>
            makeCharacter(
              `group-${index + 1}`,
              index + 1,
              member as Partial<MockCharacter>,
            ),
          ),
        ];
        await route.fulfill({ status: 200, json: listResponse() });
        return;
      }
      const characterId = rest.replace(/^\//, "");
      if (method === "PUT") {
        const body = request.postDataJSON() as Record<string, unknown>;
        state.updates.push({ id: characterId, body });
        state.characters = state.characters.map((c) =>
          c.id === characterId
            ? { ...c, ...(body as Partial<MockCharacter>) }
            : c,
        );
        await route.fulfill({
          status: 200,
          json: state.characters.find((c) => c.id === characterId),
        });
        return;
      }
      if (method === "DELETE") {
        state.characters = state.characters.filter((c) => c.id !== characterId);
        await route.fulfill({ status: 204, body: "" });
        return;
      }
      await route.fulfill({ status: 404, json: {} });
    },
  );
  await page.route("**/api/game/characters/resolve-source", async (route) => {
    state.resolveRequests.push(
      route.request().postDataJSON() as Record<string, unknown>,
    );
    await route.fulfill({
      status: 200,
      json: {
        name: "ミオ",
        appearance_natural: "",
        appearance_tags: "1girl, twintails, pink hair",
      },
    });
  });
  await page.route("**/api/game/characters/generate-profile", async (route) => {
    state.profileRequests.push(
      route.request().postDataJSON() as Record<string, unknown>,
    );
    await route.fulfill({
      status: 200,
      json: {
        personality: "明るく面倒見がよい",
        reaction_style: "cheerful",
        pronoun: "わたし",
        gender: "woman",
        interests: ["料理", "手芸"],
        tsf_attitude: "興味津々",
        memo: "料理が得意な幼なじみ",
      },
    });
  });
  await page.route("**/api/game/character-group-presets", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      state.groupCreates.push(body);
      const group = {
        id: `group-${state.groups.length + 1}`,
        name: String(body.name),
        members: state.characters
          .filter((c) => !c.is_protagonist)
          .map((c) => ({
            name: c.name,
            appearance_natural: c.appearance_natural,
            appearance_tags: c.appearance_tags,
            negative_tags: c.negative_tags,
            position: c.position,
            appearance_lock: c.appearance_lock,
            exclude_from_effects: c.exclude_from_effects,
            on_stage: c.on_stage,
            profile: c.profile,
            thumbnail_url: c.thumbnail_url,
          })),
        created_at: "2026-09-26T10:00:00",
        updated_at: "2026-09-26T10:00:00",
      };
      state.groups.push(group);
      await route.fulfill({ status: 201, json: group });
      return;
    }
    await route.fulfill({ status: 200, json: { groups: state.groups } });
  });
  return state;
}

async function gotoSession(page: Page) {
  await page.goto(`/play/${sessionId}`);
  await expect(page.getByTestId("character-panel")).toBeVisible();
}

test.describe("複数人表示の登場人物", () => {
  test("モーダルで人物を追加し、姿・ネガティブ・性格を設定する", async ({
    page,
  }) => {
    const state = await mockCastSession(page, [
      makeCharacter("hero", 0, {
        name: "ハル",
        is_protagonist: true,
        appearance_tags: "1boy",
      }),
    ]);
    await gotoSession(page);

    await page.getByTestId("character-open-cast").click();
    const modal = page.getByTestId("character-cast-modal");
    await expect(modal).toBeVisible();
    await expect(modal.getByText("登場 1 / 6")).toBeVisible();

    await modal.getByTestId("character-add-button").click();
    const detail = modal.getByTestId("character-detail");
    await expect(detail.getByRole("heading", { name: "人物1" })).toBeVisible();

    // 姿を選ぶ → セッションの現在の状態 → 外見と名前が入る
    await detail.getByTestId("character-pick-appearance").click();
    await page
      .locator(".adventure-session-picker__card-select")
      .first()
      .click();
    await expect(detail.getByTestId("character-detail-tags")).toHaveValue(
      "1girl, twintails, pink hair",
    );
    await expect(detail.getByRole("heading", { name: "ミオ" })).toBeVisible();
    expect(state.resolveRequests[0]).toEqual({ session_id: "source-session" });
    const appearanceUpdate = state.updates.find(
      (u) => u.body.appearance_tags === "1girl, twintails, pink hair",
    );
    expect(appearanceUpdate?.body.thumbnail_url).toBe(
      "/history/images/source-1",
    );

    // ネガティブタグは blur で保存する
    await detail.getByTestId("character-detail-negative").fill("glasses, hat");
    await detail.getByTestId("character-detail-name").click();
    await expect
      .poll(() => state.updates.some((u) => u.body.negative_tags))
      .toBe(true);
    expect(
      state.updates.find((u) => u.body.negative_tags)?.body.negative_tags,
    ).toBe("glasses, hat");

    // メモから性格を生成すると、結果が欄に入って保存される
    await detail
      .getByTestId("character-profile-memo")
      .fill("料理が得意な幼なじみ");
    await detail.getByTestId("character-generate-profile").click();
    await expect(detail.getByLabel("一人称")).toHaveValue("わたし");
    expect(state.profileRequests[0]).toMatchObject({
      name: "ミオ",
      memo: "料理が得意な幼なじみ",
    });
    await expect
      .poll(
        () =>
          // メモ欄の blur で先に 1 回保存されるため、最後の保存を見る
          state.updates.findLast((u) => u.body.profile)?.body.profile as
            | Record<string, unknown>
            | undefined,
      )
      .toMatchObject({ pronoun: "わたし", reaction_style: "cheerful" });

    // 主人公には性格欄の代わりに説明を出す
    await modal.getByTestId("character-cast-item").first().click();
    await expect(
      detail.getByText("主人公の性格は、キャラクターの設定"),
    ).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(modal).toBeHidden();
    const row = page.getByTestId("character-row").filter({ hasText: "ミオ" });
    await expect(row.getByText("性格")).toBeVisible();
  });

  test("登場人数の上限で ON にできず、上限超過は警告する", async ({ page }) => {
    const cast = [
      makeCharacter("hero", 0, { name: "ハル", is_protagonist: true }),
      ...[1, 2, 3, 4, 5].map((n) =>
        makeCharacter(`p${n}`, n, { name: `人物${n}` }),
      ),
      makeCharacter("p6", 6, { name: "待機", on_stage: false }),
    ];
    const state = await mockCastSession(page, cast);
    await gotoSession(page);

    await expect(page.getByTestId("character-on-stage-count")).toHaveText(
      "登場 6 / 6",
    );
    const waiting = page
      .getByTestId("character-row")
      .filter({ hasText: "待機" });
    await expect(waiting.getByTestId("character-row-on-stage")).toBeDisabled();

    // 1 人外すと ON にできる
    const first = page
      .getByTestId("character-row")
      .filter({ hasText: "人物1" });
    await first.locator(".cast-toggle").click();
    await expect
      .poll(() => state.updates.at(-1)?.body)
      .toEqual({ on_stage: false });
    await expect(waiting.getByTestId("character-row-on-stage")).toBeEnabled();
  });

  test("上限を超えて登場している人物に印を付ける", async ({ page }) => {
    await mockCastSession(page, [
      makeCharacter("hero", 0, { name: "ハル", is_protagonist: true }),
      ...[1, 2, 3, 4, 5, 6].map((n) =>
        makeCharacter(`p${n}`, n, { name: `人物${n}` }),
      ),
    ]);
    await gotoSession(page);

    await expect(page.getByTestId("character-on-stage-count")).toHaveText(
      "登場 7 / 6",
    );
    await expect(
      page.getByText("並び順の後ろの人物は生成に使われません"),
    ).toBeVisible();
    const last = page.getByTestId("character-row").filter({ hasText: "人物6" });
    await expect(last.getByText("上限外")).toBeVisible();
  });

  test("今の登場人物を組み合わせとして保存し、入れ替える", async ({ page }) => {
    const state = await mockCastSession(page, [
      makeCharacter("hero", 0, { name: "ハル", is_protagonist: true }),
      makeCharacter("sakura", 1, {
        name: "サクラ",
        negative_tags: "glasses",
      }),
    ]);
    await gotoSession(page);

    await page.getByTestId("character-open-groups").click();
    const modal = page.getByTestId("character-group-modal");
    await expect(modal).toBeVisible();
    await modal.getByTestId("character-group-name").fill("いつもの二人");
    await modal.getByTestId("character-group-save").click();
    await expect(
      modal.getByText("「いつもの二人」を保存しました"),
    ).toBeVisible();
    expect(state.groupCreates[0]).toEqual({
      name: "いつもの二人",
      from_session_id: sessionId,
    });

    // 別の人物に入れ替えてから組み合わせを呼び出す
    state.characters = [
      state.characters[0],
      makeCharacter("ren", 1, { name: "レン" }),
    ];
    page.once("dialog", (dialog) => void dialog.accept());
    await modal.getByTestId("character-group-apply").click();
    await expect(
      modal.getByText("「いつもの二人」に入れ替えました。"),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(
      page.getByTestId("character-row").filter({ hasText: "サクラ" }),
    ).toBeVisible();
    await expect(
      page.getByTestId("character-row").filter({ hasText: "レン" }),
    ).toHaveCount(0);
  });
});
