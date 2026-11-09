import { expect, type Page, test } from "@playwright/test";
import type { HakoniwaResident, HakoniwaWorld } from "../../src/apis/hakoniwa";

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
  };
}

async function mockHakoniwa(page: Page, enabled = true) {
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
  };
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
      }));
      await route.fulfill({
        json: { world, new_events: world.events, cost_usd: null },
      });
      return;
    }
    if (path.endsWith("/favorite")) {
      const event = world.events.find((item) => path.includes(`/${item.id}/`));
      if (event) event.favorite = route.request().postDataJSON().favorite;
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
