import { expect, type Page, test } from "@playwright/test";

const TRACKS = [
  {
    key: "daily",
    file: "scene06_daily.ogg",
    description: "everyday ordinary scenes; also the fallback",
    credit: "SUNO v4.5-all で作成",
    url: "/adventure/bgm/audio/scene06_daily.ogg",
  },
  {
    key: "dark",
    file: "scene05_dark.ogg",
    description: "dark, ominous, sad, dangerous, or serious events",
    credit: "SUNO v4.5-all で作成",
    url: "/adventure/bgm/audio/scene05_dark.ogg",
  },
  {
    key: "bar",
    file: "scene08_bar.ogg",
    description: "cafes, bars, lounges, restaurants",
    credit: "SUNO v4.5-all で作成",
    url: "/adventure/bgm/audio/scene08_bar.ogg",
  },
];

async function enableAdventure(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("novelai_api_key_consent", "true");
    window.localStorage.setItem(
      "app_settings",
      JSON.stringify({ experimentalAdventureEnabled: true }),
    );
  });
}

async function mockBgmCatalog(page: Page, tracks = TRACKS) {
  await page.route("**/api/adventure/bgm", async (route) => {
    await route.fulfill({ json: { default_key: "daily", tracks } });
  });
  // 音声本体は取得させない。再生成否に依存するアサーションは行わない
  await page.route("**/api/adventure/bgm/audio/**", async (route) => {
    await route.abort();
  });
}

test("side menu opens the BGM test screen and lists every track", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockBgmCatalog(page);
  await page.goto("/play/new");

  const menuItem = page.getByRole("button", { name: "BGMテスト" });
  await expect(menuItem).toBeVisible();
  await menuItem.click();

  await expect(page).toHaveURL(/\/bgm-test$/);
  await expect(
    page.getByRole("heading", { name: "BGMテスト", level: 1 }),
  ).toBeVisible();

  for (const track of TRACKS) {
    await expect(page.getByText(track.file, { exact: true })).toBeVisible();
    await expect(
      page.getByText(track.description, { exact: true }),
    ).toBeVisible();
  }
});

test("every track shows its own credit even when they all match", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockBgmCatalog(page);
  await page.goto("/bgm-test");

  // 全曲が同値でもヘッダーへ集約せず、各行に出す
  await expect(
    page.getByText("SUNO v4.5-all で作成", { exact: true }),
  ).toHaveCount(TRACKS.length);
});

test("credit text is rendered verbatim and omitted when unset", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockBgmCatalog(page, [
    TRACKS[0],
    { ...TRACKS[1], credit: "○○の音楽素材 より配布" },
    // 自作曲など表記不要な曲は credit を持たない
    { ...TRACKS[2], credit: undefined },
  ]);
  await page.goto("/bgm-test");

  const track = (file: string) =>
    page.locator(".bgm-test-screen__track").filter({ hasText: file });

  // 生成AI以外の言い回しも、カタログの文面のまま出る
  await expect(track("scene06_daily.ogg")).toContainText(
    "SUNO v4.5-all で作成",
  );
  await expect(track("scene05_dark.ogg")).toContainText(
    "○○の音楽素材 より配布",
  );
  await expect(
    track("scene08_bar.ogg").locator(".bgm-test-screen__track-credit"),
  ).toHaveCount(0);
});

test("selecting a track moves the active state and updates the player", async ({
  page,
}) => {
  await enableAdventure(page);
  await mockBgmCatalog(page);
  await page.goto("/bgm-test");

  const player = page.getByRole("region", { name: "BGMプレイヤー" });
  await expect(player).toContainText("曲が選択されていません");

  const darkTrack = page
    .locator(".bgm-test-screen__track")
    .filter({ hasText: "scene05_dark.ogg" });
  await darkTrack.click();

  await expect(darkTrack).toHaveClass(/is-active/);
  await expect(player).toContainText("scene05_dark.ogg");
});

test("bgm test screen is gated behind the TSF scenario setting", async ({
  page,
}) => {
  await mockBgmCatalog(page);
  await page.goto("/bgm-test");

  await expect(page).toHaveURL(/\/play\/new$/);
});
