import { expect, type Page, test } from "@playwright/test";
import type {
  HakoniwaArea,
  HakoniwaChatEntry,
  HakoniwaResident,
  HakoniwaWorld,
} from "../../src/apis/hakoniwa";

function area(id: string, name: string, file: string): HakoniwaArea {
  return {
    id,
    name,
    background_url: `/hakoniwa-assets/${file}`,
    slots: [180, 470, 760, 1040].map((x) => ({
      x,
      y: 700,
      furniture_id: null,
    })),
  };
}

function resident(id: string, name: string): HakoniwaResident {
  const avatar = `/hakoniwa-assets/avatar_${id}.png`;
  return {
    id,
    name,
    source: "preset",
    preset_id: id,
    character_preset_id: null,
    gender: id === "ren" ? "male" : "female",
    body_gender: id === "ren" ? "male" : "female",
    age: "20代後半",
    job: "住民",
    personality: "穏やか",
    pronoun: id === "ren" ? "俺" : "私",
    appearance_text: "",
    base_tags: "",
    dress_text: "",
    dress_tags: "",
    mood: 50,
    affinities: {},
    transformation: null,
    transformation_history: [],
    swapped_with: null,
    display_avatar_url: avatar,
    display_kind: "base",
    display_owner_id: id,
    own_avatar_url: avatar,
    avatar_url: avatar,
    dress_avatar_url: `/hakoniwa-assets/avatar_${id}_dress.png`,
    current_area: "living",
    adaptation: null,
    world_adaptation: null,
    remnant: null,
    memories: [],
  };
}

async function mockHakoniwa(page: Page, enabled = true, dissonance = 0) {
  const world: HakoniwaWorld = {
    id: "test-world",
    name: "検証用の星屑荘",
    day: 1,
    created_at: null,
    updated_at: null,
    background_url: "/hakoniwa-assets/room.png",
    image_model: "default",
    image_model_effective: "nai-diffusion-4-5-full",
    image_model_default: "nai-diffusion-4-5-full",
    image_model_options: ["nai-diffusion-4-5-full"],
    transparency: "removal",
    active_rules: [],
    swap_pair: null,
    rule_cards: [
      {
        id: "swap",
        name: "入れ替わりの朝",
        description: "体が入れ替わる",
        custom: false,
        active: false,
      },
      {
        id: "dress",
        name: "ドレスの掟",
        description: "ドレスを着る",
        custom: false,
        active: false,
      },
    ],
    residents: [resident("aoi", "高瀬 葵"), resident("ren", "苑田 蓮")],
    events: [],
    areas: [
      area("living", "リビング", "room.png"),
      area("garden", "庭", "area_garden.png"),
      area("study", "書斎", "area_study.png"),
    ],
    furniture_catalog: [
      {
        id: "lamp",
        name: "ランプ",
        url: "/hakoniwa-assets/furniture_lamp.png",
      },
      {
        id: "plush",
        name: "ぬいぐるみ",
        url: "/hakoniwa-assets/furniture_plush.png",
      },
    ],
    last_digest: null,
    dissonance: {
      enabled: true,
      value: dissonance,
      stage: dissonance >= 50 ? "probing" : "stillness",
      acknowledged: false,
      next_stage: dissonance >= 50 ? "confrontation" : "stirring",
      remaining: dissonance >= 50 ? 80 - dissonance : 20 - dissonance,
    },
    story_arcs: [],
    combo_look: null,
    world_memo: "",
    intervention: { selected: "watch", choices: ["watch", "nudge", "rewrite"] },
  };
  const chats: Record<string, HakoniwaChatEntry[]> = {};
  await page.addInitScript((flag) => {
    localStorage.setItem("novelai_api_key_consent", "true");
    localStorage.setItem(
      "app_settings",
      JSON.stringify({ experimentalHakoniwaEnabled: flag, language: "ja" }),
    );
  }, enabled);
  // API をすべて捕捉し、実サーバーや課金される生成処理へ到達させない。
  await page.route(/\/(api\/|health|novelai\/)/, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/health") {
      await route.fulfill({
        json: {
          status: "ok",
          image_provider: "comfyui",
          text_provider: "openrouter",
        },
      });
      return;
    }
    if (!path.startsWith("/api/hakoniwa/")) {
      await route.fulfill({ json: {} });
      return;
    }
    if (path.endsWith("/catalog")) {
      await route.fulfill({
        json: {
          presets: world.residents,
          rule_cards: world.rule_cards,
          background_url: world.background_url,
          image_model_options: world.image_model_options,
        },
      });
      return;
    }
    if (path.endsWith("/worlds")) {
      await route.fulfill({
        json: route.request().method() === "POST" ? world : { worlds: [] },
      });
      return;
    }
    if (path.endsWith("/day")) {
      world.day += 1;
      world.events = Array.from({ length: 3 }, (_, index) => ({
        id: `event-${index}`,
        day: 1,
        title: `出来事${index + 1}`,
        narration: "リビングで住民たちが朝の挨拶を交わした。",
        lines: [
          { speaker: "aoi", text: "今日はいい天気だね。" },
          { speaker: "ren", text: "庭の花も咲いている。" },
        ],
        participants: ["aoi", "ren"],
        mood_delta: {},
        affinity_delta: 0,
        source: "template",
        favorite: false,
        area: "living",
        scene_image: null,
        scene_image_url: null,
        scene_suggestion:
          index === 0 ? { level: "normal", reason: "手が触れ合う" } : null,
      }));
      world.last_digest = {
        day: 1,
        highlight: {
          event_id: "event-0",
          title: "出来事1",
          reason: "trio",
          participants: ["aoi", "ren"],
        },
        changes: [{ type: "mood", id: "aoi", delta: 9, mood: 59 }],
        hint: { type: "no_rules" },
      };
      await route.fulfill({
        json: {
          world,
          new_events: world.events,
          digest: world.last_digest,
          cost_usd: null,
        },
      });
      return;
    }
    if (path.endsWith("/furniture")) {
      const body = route.request().postDataJSON();
      for (const item of world.areas) {
        for (const slot of item.slots) {
          if (body.furniture_id && slot.furniture_id === body.furniture_id) {
            slot.furniture_id = null;
          }
        }
      }
      const target = world.areas.find((item) => item.id === body.area_id);
      const slot = target?.slots[body.slot];
      if (slot) slot.furniture_id = body.furniture_id;
    }
    if (path.endsWith("/favorite")) {
      const event = world.events.find((item) => path.includes(`/${item.id}/`));
      if (event) event.favorite = route.request().postDataJSON().favorite;
    }
    if (path.endsWith("/custom-rules") && route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      world.rule_cards.push({
        id: "custom_rule_maid",
        name: body.name,
        description: body.text,
        custom: true,
        active: false,
        appearance_text: body.appearance_text,
        appearance_tags: "maid outfit, headdress",
        look: { ready: 0, stale: 0, total: world.residents.length },
      });
    }
    if (path.endsWith("/look") || path.endsWith("/combo-look")) {
      const combo = path.endsWith("/combo-look");
      for (const item of world.residents) {
        item.display_kind = combo ? "combo" : "rule";
        item.display_avatar_url = item.dress_avatar_url;
      }
      if (combo && world.combo_look) {
        world.combo_look.ready = world.residents.length;
      }
      const card = world.rule_cards.find((item) => item.custom);
      if (!combo && card?.look) card.look.ready = world.residents.length;
      await route.fulfill({
        json: {
          world,
          generated: world.residents.length,
          failed: 0,
          cost_usd: null,
        },
      });
      return;
    }
    if (path.endsWith("/intervention")) {
      world.intervention.selected = route.request().postDataJSON().choice;
    }
    if (path.endsWith("/touch")) {
      const body = route.request().postDataJSON();
      await route.fulfill({
        json: {
          world,
          resident_id: "aoi",
          part: body.part,
          text: "ん……撫でられると、なんだか落ち着くかも",
          source: "template",
          mood_delta: 2,
          cost_usd: null,
        },
      });
      return;
    }
    if (path.endsWith("/chat")) {
      const residentId = path.split("/").at(-2) ?? "";
      const history = chats[residentId] ?? [];
      if (route.request().method() === "GET") {
        await route.fulfill({ json: { resident_id: residentId, history } });
        return;
      }
      const message = route.request().postDataJSON().message as string;
      const newEvents: HakoniwaWorld["events"] = [];
      let reply: HakoniwaChatEntry;
      history.push({ role: "player", text: message });
      if (message.includes("着替えて")) {
        const event = {
          id: "chat-transform",
          day: world.day,
          title: "高瀬 葵の変身",
          narration: "高瀬 葵の姿が、その場で変わった。",
          lines: [],
          participants: ["aoi"],
          mood_delta: {},
          affinity_delta: 0,
          source: "player",
          kind: "transform",
          favorite: false,
          area: "living",
        };
        world.events.push(event);
        newEvents.push(event);
        history.push({
          role: "system",
          text: "変身として実行しました:「メイド服に着替えて」。",
          kind: "alteration",
        });
        reply = { role: "resident", text: "ど、どうかな……似合ってる？" };
      } else {
        reply = { role: "resident", text: "おはよう。今日も配達、がんばるね" };
      }
      history.push(reply);
      chats[residentId] = history;
      await route.fulfill({
        json: {
          world,
          reply,
          history,
          alteration: {
            action: newEvents.length ? "transform" : "none",
            instruction: newEvents.length ? message : "",
            executed: newEvents.length > 0,
            needs_confirmation: false,
          },
          new_events: newEvents,
          cost_usd: null,
        },
      });
      return;
    }
    if (path.endsWith("/settings")) {
      const body = route.request().postDataJSON();
      if (typeof body.world_memo === "string")
        world.world_memo = body.world_memo;
      if (typeof body.dissonance_enabled === "boolean") {
        world.dissonance.enabled = body.dissonance_enabled;
      }
    }
    if (path.includes("/rules/")) {
      const id = path.split("/").at(-1);
      const card = world.rule_cards.find((item) => item.id === id);
      if (card) card.active = route.request().postDataJSON().active;
      world.active_rules = world.rule_cards
        .filter((item) => item.active)
        .map((item) => item.id);
      world.swap_pair = world.active_rules.includes("swap")
        ? ["aoi", "ren"]
        : null;
      for (const item of world.residents) {
        const owner = world.swap_pair
          ? world.residents.find((other) => other.id !== item.id)
          : item;
        if (!owner) continue;
        item.display_owner_id = owner.id;
        item.swapped_with = world.swap_pair ? owner.id : null;
        item.body_gender = owner.gender;
        item.display_kind = world.active_rules.includes("dress")
          ? "dress"
          : "base";
        item.display_avatar_url =
          item.display_kind === "dress"
            ? owner.dress_avatar_url
            : owner.avatar_url;
      }
      // 書き換えで違和感が溜まり、80 に達したら対面の出来事が起きる
      const newEvents: HakoniwaWorld["events"] = [];
      if (world.dissonance.enabled && !world.dissonance.acknowledged) {
        world.dissonance.value += 8;
        if (world.dissonance.value >= 80) {
          const event = {
            id: "confrontation",
            day: world.day,
            title: "書き手への呼びかけ",
            narration: "二人は天井へ向かって声を上げた。",
            lines: [
              { speaker: "aoi", text: "聞こえますか。" },
              { speaker: "ren", text: "理由が知りたいんです。" },
            ],
            participants: ["aoi", "ren"],
            mood_delta: {},
            affinity_delta: 3,
            source: "template",
            kind: "confrontation",
            favorite: false,
            area: "living",
            scene_suggestion: {
              level: "strong" as const,
              reason: "物語の転機です",
            },
          };
          world.events.push(event);
          newEvents.push(event);
          world.dissonance = {
            ...world.dissonance,
            value: 40,
            stage: "probing",
            acknowledged: true,
          };
          for (const item of world.residents) {
            item.memories = [
              {
                day: world.day,
                kind: "confrontation",
                text: "世界を書き換えている存在（書き手）へ呼びかけた",
              },
            ];
          }
        }
      }
      const customs = world.rule_cards.filter(
        (item) => item.custom && item.active,
      );
      world.combo_look =
        customs.length > 0 && world.active_rules.includes("dress")
          ? {
              rule_ids: customs.map((item) => item.id),
              names: customs.map((item) => item.name),
              includes_dress: true,
              untagged_names: [],
              ready: 0,
              stale: 0,
              total: world.residents.length,
            }
          : null;
      await route.fulfill({
        json: { world, new_events: newEvents, cost_usd: null },
      });
      return;
    }
    if (path.endsWith("/greet")) {
      await route.fulfill({
        json: {
          resident_id: "aoi",
          text: "今日もよろしく。",
          source: "template",
          cost_usd: null,
        },
      });
      return;
    }
    await route.fulfill({ json: world });
  });
  return world;
}

test("機能OFFでは通常プレイへ戻る", async ({ page }) => {
  await mockHakoniwa(page, false);
  await page.goto("/hakoniwa");
  await expect(page).toHaveURL(/\/play\/new$/);
});

test("世界作成・台詞送り・年代記・掟・住民の一言", async ({ page }) => {
  await mockHakoniwa(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/hakoniwa");
  await page.getByRole("button", { name: "この顔ぶれで世界をつくる" }).click();
  await expect(page).toHaveURL(/\/hakoniwa\/test-world$/);
  // 開発サーバーでは StrictMode の再マウントで一時的にキャンバスが2枚になるため、1枚に落ち着くのを待つ
  await expect(page.locator(".hakoniwa-stage__canvas canvas")).toHaveCount(1);
  await expect(page.locator(".hakoniwa-stage__canvas canvas")).toBeVisible();
  await page.getByRole("button", { name: "1日進める", exact: true }).click();
  await expect(page.locator(".hakoniwa-caption__progress")).toHaveText(
    "1 / 3 件目",
  );
  await page.getByTestId("hakoniwa-stage").click();
  await expect(page.locator(".hakoniwa-bubble__text")).toHaveText(
    "今日はいい天気だね。",
  );
  await page.keyboard.press("Enter");
  await expect(page.locator(".hakoniwa-bubble__text")).toHaveText(
    "庭の花も咲いている。",
  );
  await page.keyboard.press("Escape");
  await expect(page.locator(".hakoniwa-caption")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "お気に入りに入れる" }),
  ).toHaveCount(3);
  await page
    .getByRole("button", { name: "お気に入りに入れる" })
    .first()
    .click();
  await expect(
    page.getByRole("button", { name: "お気に入りから外す" }),
  ).toHaveCount(1);
  await page.getByRole("tab", { name: "掟", exact: true }).click();
  await page
    .getByRole("checkbox", { name: "入れ替わりの朝を有効にする" })
    .click();
  await expect(
    page.getByRole("checkbox", { name: "入れ替わりの朝を有効にする" }),
  ).toBeChecked();
  await page.getByRole("checkbox", { name: "ドレスの掟を有効にする" }).click();
  await expect(
    page.getByRole("checkbox", { name: "ドレスの掟を有効にする" }),
  ).toBeChecked();
  await page.getByRole("tab", { name: "住民", exact: true }).click();
  const aoi = page.getByRole("button", { name: /高瀬 葵/ });
  await expect(aoi.locator("img")).toHaveAttribute(
    "src",
    /avatar_ren_dress\.png/,
  );
  await aoi.click();
  await page.getByRole("button", { name: "話しかける", exact: true }).click();
  await expect(page.locator(".hakoniwa-bubble__text")).toHaveText(
    "今日もよろしく。",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByTestId("hakoniwa-stage")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("ダイアログの上のクリックで住民が反応せず、広い画面でも1日進めるが見える", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1920, height: 950 });
  await mockHakoniwa(page);
  // 動きを減らす設定では住民が初期位置から動かない(クリック位置を決められる)
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/hakoniwa");
  await page.getByRole("button", { name: "この顔ぶれで世界をつくる" }).click();
  // 開発サーバーでは StrictMode の再マウントで一時的にキャンバスが2枚になるため、1枚に落ち着くのを待つ
  await expect(page.locator(".hakoniwa-stage__canvas canvas")).toHaveCount(1);
  await expect(page.locator(".hakoniwa-stage__canvas canvas")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "1日進める", exact: true }),
  ).toBeInViewport();
  // 「1日進める」は部屋の下の行の右端(明日の介入より右)
  const advanceRow = await page
    .locator(".hakoniwa-world__advance")
    .boundingBox();
  const advanceButton = await page
    .getByRole("button", { name: "1日進める", exact: true })
    .boundingBox();
  const interventionGroup = await page
    .getByRole("group", { name: "明日の介入" })
    .boundingBox();
  if (!advanceRow || !advanceButton || !interventionGroup) {
    throw new Error("advance row not found");
  }
  expect(Math.round(advanceButton.x + advanceButton.width)).toBe(
    Math.round(advanceRow.x + advanceRow.width),
  );
  expect(advanceButton.x).toBeGreaterThan(
    interventionGroup.x + interventionGroup.width,
  );

  await page.getByRole("tab", { name: "掟", exact: true }).click();
  await page.getByRole("button", { name: "掟を書く" }).click();
  await page.getByLabel("掟の名前").fill("猫の日");
  await page.getByLabel("本文").fill("全員が猫耳を付けて過ごす");

  // 2人目(苑田 蓮)の初期位置: 部屋の横 3/4、足元 y=697 / 832、高さ 458 の中ほど
  const room = await page.getByTestId("hakoniwa-stage").boundingBox();
  if (!room) throw new Error("room not found");
  await page.mouse.click(
    room.x + room.width * 0.75,
    room.y + room.height * ((697 - 458 / 2) / 832),
  );

  await expect(page.locator(".hakoniwa-form-dialog")).toBeVisible();
  await expect(page.getByLabel("掟の名前")).toHaveValue("猫の日");
  await expect(
    page.getByRole("tab", { name: "掟", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
});

test("右パネルのタブは中身が長くても縮まず、ページ全体はスクロールしない", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await mockHakoniwa(page);
  await page.goto("/hakoniwa");
  await page.getByRole("button", { name: "この顔ぶれで世界をつくる" }).click();
  const tabs = page.locator(".hakoniwa-tabs");
  await expect(tabs).toBeVisible();

  const measure = () =>
    page.evaluate(() => {
      const bar = document.querySelector(".hakoniwa-tabs") as HTMLElement;
      const root = document.documentElement;
      return {
        height: Math.round(bar.getBoundingClientRect().height),
        barOverflow: bar.scrollHeight - bar.clientHeight,
        pageOverflow: root.scrollHeight - root.clientHeight,
      };
    });
  const initial = await measure();
  for (const name of ["住民", "掟", "家具", "設定", "年代記"]) {
    await page.getByRole("tab", { name, exact: true }).click();
    await expect(page.getByRole("tab", { name, exact: true })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(await measure(), name).toEqual({
      height: initial.height,
      barOverflow: 0,
      pageOverflow: 0,
    });
  }
});

test("場所の切り替え・家具・1日のまとめ・ADV で読む", async ({ page }) => {
  await mockHakoniwa(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/hakoniwa");
  await page.getByRole("button", { name: "この顔ぶれで世界をつくる" }).click();
  await expect(page.locator(".hakoniwa-stage__canvas canvas")).toHaveCount(1);

  // 場所のチップ: 住民の人数が出て、押すと表示する場所が替わる
  const living = page.getByRole("tab", { name: /^リビング/ });
  const garden = page.getByRole("tab", { name: /^庭/ });
  await expect(living).toHaveAttribute("aria-selected", "true");
  await expect(living).toContainText("2人");
  await garden.click();
  await expect(garden).toHaveAttribute("aria-selected", "true");
  await expect(garden).toContainText("0人");

  // 家具は1点物: 別の場所へ置くと移る
  await page.getByRole("tab", { name: "家具", exact: true }).click();
  const areas = page.locator(".hakoniwa-furniture__area");
  await areas.nth(0).getByLabel("置き場所 1").selectOption("lamp");
  await expect(areas.nth(0).getByLabel("置き場所 1")).toHaveValue("lamp");
  await expect(
    areas.nth(1).getByLabel("置き場所 1").locator("option[value=lamp]"),
  ).toHaveText("ランプ（いま: リビングの置き場所 1）");
  await areas.nth(1).getByLabel("置き場所 1").selectOption("lamp");
  await expect(areas.nth(1).getByLabel("置き場所 1")).toHaveValue("lamp");
  await expect(areas.nth(0).getByLabel("置き場所 1")).toHaveValue("");

  // 1日進めると出来事の場所(リビング)へ切り替わり、再生後にまとめが出る
  await page.getByRole("tab", { name: "年代記", exact: true }).click();
  await page.getByRole("button", { name: "1日進める", exact: true }).click();
  await expect(page.locator(".hakoniwa-caption")).toBeVisible();
  await expect(living).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Escape");
  const digest = page.locator(".hakoniwa-digest--overlay");
  await expect(digest).toContainText("1日目のまとめ");
  await expect(digest).toContainText("3人がそろった");
  await expect(digest).toContainText("高瀬 葵の気分が上向いた");
  await expect(digest).toContainText("掟がひとつも有効になっていません");

  // まとめの山場から ADV で読む: クリック・Enter で送り、最後は「閉じる」
  await digest.getByRole("button", { name: /ADVで見る/ }).click();
  const adv = page.getByTestId("hakoniwa-adv");
  await expect(adv).toBeVisible();
  await expect(adv.locator(".hakoniwa-adv__text")).toHaveText(
    "リビングで住民たちが朝の挨拶を交わした。",
  );
  await expect(adv.locator(".hakoniwa-adv__suggest")).toContainText(
    "手が触れ合う",
  );
  await adv.locator(".hakoniwa-adv__background").click();
  await expect(adv.locator(".hakoniwa-adv__speaker")).toHaveText("高瀬 葵");
  await expect(adv.locator(".hakoniwa-adv__text")).toHaveText(
    "「今日はいい天気だね。」",
  );
  await adv.getByRole("button", { name: "ウィンドウを非表示" }).click();
  await expect(adv.locator(".hakoniwa-adv__window")).toHaveCount(0);
  await adv.getByRole("button", { name: "ウィンドウを表示" }).click();
  await expect(adv.locator(".hakoniwa-adv__text")).toHaveText(
    "「今日はいい天気だね。」",
  );
  await page.keyboard.press("Enter");
  await expect(adv.locator(".hakoniwa-adv__progress")).toHaveText("3 / 3");
  await adv.getByRole("button", { name: "閉じる", exact: true }).click();
  await expect(adv).toHaveCount(0);

  // 年代記からも開け、Esc で閉じる。まとめは年代記の先頭にも残る
  await digest.getByRole("button", { name: "まとめを閉じる" }).click();
  await expect(digest).toHaveCount(0);
  await expect(page.locator(".hakoniwa-chronicle__digest")).toContainText(
    "直近のまとめ（1日目）",
  );
  await expect(page.locator(".hakoniwa-event__place").first()).toHaveText(
    "リビング",
  );
  await page
    .locator(".hakoniwa-event")
    .first()
    .getByRole("button", { name: /ADVで見る/ })
    .click();
  await expect(adv).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(adv).toHaveCount(0);
});

test("掟の切り替えで対面が起き、部屋で再生されて記憶に残る", async ({
  page,
}) => {
  await mockHakoniwa(page, true, 72);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/hakoniwa");
  await page.getByRole("button", { name: "この顔ぶれで世界をつくる" }).click();
  await expect(page.locator(".hakoniwa-stage__canvas canvas")).toHaveCount(1);

  const chip = page.getByTestId("hakoniwa-dissonance");
  await expect(chip).toHaveText("違和感: 探り合い 72");
  await expect(chip).toHaveAttribute("title", /「対面」まであと8/);

  await page.getByRole("tab", { name: "掟", exact: true }).click();
  await page.getByRole("checkbox", { name: "ドレスの掟を有効にする" }).click();
  await expect(page.locator(".hakoniwa-caption__title")).toHaveText(
    "書き手への呼びかけ",
  );
  await page.keyboard.press("Escape");
  await expect(page.locator(".hakoniwa-caption")).toHaveCount(0);
  await expect(chip).toHaveText("違和感: 公認 40");

  // 対面の出来事が増えたので、年代記のタブには未読の数が付いている
  await page.getByRole("tab", { name: /^年代記\+1$/ }).click();
  await expect(
    page.locator(".hakoniwa-event").first().locator(".hakoniwa-badge--accent"),
  ).toHaveText("対面");
  await page.getByRole("tab", { name: "住民", exact: true }).click();
  await page.getByRole("button", { name: /高瀬 葵/ }).click();
  await expect(page.locator(".hakoniwa-resident__memories")).toContainText(
    "世界を書き換えている存在（書き手）へ呼びかけた",
  );

  await page.getByRole("tab", { name: "設定", exact: true }).click();
  await page.getByRole("checkbox", { name: "世界の違和感を使う" }).click();
  await expect(chip).toHaveCount(0);
});

test("自作の掟の姿と、ドレスの掟と重ねた複合の姿を生成する", async ({
  page,
}) => {
  await mockHakoniwa(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/hakoniwa");
  await page.getByRole("button", { name: "この顔ぶれで世界をつくる" }).click();
  await expect(page.locator(".hakoniwa-stage__canvas canvas")).toHaveCount(1);

  await page.getByRole("tab", { name: "掟", exact: true }).click();
  await page.getByRole("button", { name: "掟を書く" }).click();
  await page.getByLabel("掟の名前").fill("メイドの日");
  await page.getByLabel("本文").fill("全員がメイド服で過ごす");
  await page
    .getByLabel("見た目の説明（任意）")
    .fill("全員がメイド服とヘッドドレス姿になる");
  await page.getByRole("button", { name: "保存する" }).click();

  const rule = page.locator(".hakoniwa-rule").filter({ hasText: "メイドの日" });
  await expect(rule).toContainText(
    "見た目: 全員がメイド服とヘッドドレス姿になる",
  );
  await expect(rule.locator(".hakoniwa-rule__appearance-tags")).toHaveText(
    "maid outfit, headdress",
  );
  await rule.getByRole("checkbox", { name: "メイドの日を有効にする" }).click();
  await rule.getByRole("button", { name: "姿を生成（2人分）" }).click();
  const dialog = page.getByRole("dialog", { name: "姿を生成しますか？" });
  await expect(dialog).toContainText("画像2枚");
  await dialog.getByRole("button", { name: "2人分を生成" }).click();
  await expect(rule).toContainText("姿: 全員ぶん生成済み");
  await expect(
    rule.getByRole("button", { name: "描き直す（2人分）" }),
  ).toBeVisible();

  await page.getByRole("checkbox", { name: "ドレスの掟を有効にする" }).click();
  const combo = page.locator(".hakoniwa-rules__combo");
  await expect(combo).toContainText("メイドの日＋ドレスの掟");
  await combo.getByRole("button", { name: "姿を生成（2人分）" }).click();
  await page
    .getByRole("dialog", { name: "姿を生成しますか？" })
    .getByRole("button", { name: "2人分を生成" })
    .click();
  await expect(combo).toContainText("姿: 全員ぶん生成済み");

  await page.getByRole("tab", { name: "住民", exact: true }).click();
  await page.getByRole("button", { name: /高瀬 葵/ }).click();
  await expect(page.locator(".hakoniwa-resident__states")).toContainText(
    "複合の姿",
  );
});

test("明日の介入・世界のメモ・立ち絵に触れる・箱庭の中で話す", async ({
  page,
}) => {
  await mockHakoniwa(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/hakoniwa");
  await page.getByRole("button", { name: "この顔ぶれで世界をつくる" }).click();
  await expect(page.locator(".hakoniwa-stage__canvas canvas")).toHaveCount(1);

  const intervention = page.getByRole("group", { name: "明日の介入" });
  await intervention.getByRole("button", { name: "書き換えを強める" }).click();
  await expect(
    intervention.getByRole("button", { name: "書き換えを強める" }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".hakoniwa-world__advance")).toContainText(
    "物語が大きく動き",
  );

  await page.getByRole("tab", { name: "設定", exact: true }).click();
  await page.getByLabel("世界のメモ").fill("季節は冬で、毎晩雪が降っている");
  await page.getByRole("button", { name: "メモを保存" }).click();
  await expect(page.getByRole("button", { name: "メモを保存" })).toBeDisabled();

  await page.getByRole("tab", { name: "住民", exact: true }).click();
  await page.getByRole("button", { name: /高瀬 葵/ }).click();
  await page.getByTitle("立ち絵を拡大して触れる").click();
  const touch = page.getByTestId("hakoniwa-touch");
  const figure = page.getByTestId("hakoniwa-touch-figure");
  const box = await figure.boundingBox();
  if (!box) throw new Error("figure not found");
  await page.mouse.click(box.x + box.width / 2, box.y + box.height * 0.1);
  await expect(touch.locator(".hakoniwa-touch__reaction")).toContainText(
    "頭「ん……撫でられると、なんだか落ち着くかも」",
  );
  await page.keyboard.press("Escape");
  await expect(touch).toHaveCount(0);

  await page.getByRole("button", { name: "会話を始める" }).click();
  const chat = page.getByTestId("hakoniwa-chat");
  await expect(chat).toContainText("高瀬 葵に話しかけてみましょう。");
  await chat.getByLabel("高瀬 葵への言葉").fill("おはよう");
  await chat.getByRole("button", { name: "送る" }).click();
  await expect(chat.locator(".hakoniwa-adv__text")).toHaveText(
    "「おはよう。今日も配達、がんばるね」",
  );
  await chat.getByLabel("高瀬 葵への言葉").fill("メイド服に着替えて");
  await chat.getByRole("button", { name: "送る" }).click();
  await expect(chat.locator(".hakoniwa-adv__text")).toHaveText(
    "「ど、どうかな……似合ってる？」",
  );
  await chat.getByRole("button", { name: "ログ" }).click();
  await expect(chat.locator(".hakoniwa-chat__entry")).toHaveCount(5);
  await expect(chat.locator(".hakoniwa-chat__log")).toContainText(
    "変身として実行しました",
  );
  await chat.getByRole("button", { name: "ログを閉じる" }).click();
  await chat.getByRole("button", { name: "会話を終える" }).click();
  await expect(chat).toHaveCount(0);
  // 会話の中で変身した出来事は、閉じたあと部屋で再生される
  await expect(page.locator(".hakoniwa-caption__title")).toHaveText(
    "高瀬 葵の変身",
  );
});
