import { describe, expect, it } from "vitest";
import type { SettingsState } from "../../contexts/SettingsContext";
import i18n, { type TranslationKey } from "../../i18n";
import {
  buildSearchTexts,
  countMatchesByCategory,
  findMatchingItemIds,
  getItemIdsIn,
  getUnavailableItemIds,
  normalizeSearchText,
  SETTINGS_CATEGORIES,
  SETTINGS_ITEMS,
  type SettingsItemId,
} from "./settingsSearchIndex";

const tJa = i18n.getFixedT("ja");
const tEn = i18n.getFixedT("en");
const jaTexts = buildSearchTexts((key: TranslationKey) => tJa(key));
const enTexts = buildSearchTexts((key: TranslationKey) => tEn(key));

function makeState(overrides: Partial<SettingsState> = {}): SettingsState {
  return {
    imageProvider: "selfhost",
    enableSurroundingsImage: false,
    novelaiTier: null,
    anlasBalance: null,
    ...overrides,
  } as SettingsState;
}

const noneUnavailable = new Set<SettingsItemId>();

describe("normalizeSearchText", () => {
  it("カタカナ/ひらがな・全角/半角・大文字/小文字の違いを無視する", () => {
    expect(normalizeSearchText("フォント")).toBe("ふぉんと");
    expect(normalizeSearchText("ﾌｫﾝﾄ")).toBe("ふぉんと");
    expect(normalizeSearchText("ＶＲＭ")).toBe("vrm");
    expect(normalizeSearchText("  Live2D　Cubism ")).toBe("live2d cubism");
  });
});

describe("SETTINGS_ITEMS", () => {
  it("ID が重複していない", () => {
    const ids = SETTINGS_ITEMS.map((item) => item.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("すべてのカテゴリに1件以上の項目がある", () => {
    for (const category of SETTINGS_CATEGORIES) {
      expect(SETTINGS_ITEMS.some((item) => item.category === category.id)).toBe(
        true,
      );
    }
  });
});

describe("findMatchingItemIds", () => {
  it("クエリが空なら検索していない扱い(null)を返す", () => {
    expect(findMatchingItemIds("", jaTexts, noneUnavailable)).toBeNull();
    expect(findMatchingItemIds("   ", jaTexts, noneUnavailable)).toBeNull();
  });

  it("ひらがな入力でカタカナのラベルに一致する", () => {
    const matched = findMatchingItemIds("ふぉんと", jaTexts, noneUnavailable);
    expect(matched).toEqual(new Set(["fontFamily"]));
  });

  it("言語によらない検索語(VRM, TTS)で一致する", () => {
    expect(findMatchingItemIds("vrm", jaTexts, noneUnavailable)).toEqual(
      new Set(["avatarModels"]),
    );
    expect(findMatchingItemIds("TTS", enTexts, noneUnavailable)).toEqual(
      new Set(["speech"]),
    );
  });

  it("空白区切りの語はすべて含む項目だけに一致する(AND)", () => {
    const single = findMatchingItemIds("通知", jaTexts, noneUnavailable);
    const both = findMatchingItemIds("通知 実績", jaTexts, noneUnavailable);
    expect(single?.has("achievementNotify")).toBe(true);
    expect(single?.has("realityAttributeNotify")).toBe(true);
    expect(both).toEqual(new Set(["achievementNotify"]));
  });

  it("カテゴリ見出しに一致すると、そのカテゴリの項目すべてに一致する", () => {
    const matched = findMatchingItemIds(
      tJa("settings.notifySection"),
      jaTexts,
      noneUnavailable,
    );
    expect(matched?.has("achievementNotify")).toBe(true);
    expect(matched?.has("realityAttributeNotify")).toBe(true);
  });

  it("一致しなければ空集合を返す", () => {
    expect(
      findMatchingItemIds("zzzzzz-no-match", jaTexts, noneUnavailable),
    ).toEqual(new Set());
  });

  it("表示しない項目は一致から除く", () => {
    const unavailable = getUnavailableItemIds({
      state: makeState(),
      isNovelaiV5Active: false,
    });
    const matched = findMatchingItemIds("NovelAI", jaTexts, unavailable);
    expect(matched?.has("novelaiImageModelNsfw")).toBe(false);
    expect(matched?.has("novelaiTextModel")).toBe(false);
  });
});

describe("getUnavailableItemIds", () => {
  it("今の画面と同じ条件で項目を隠す", () => {
    const selfhost = getUnavailableItemIds({
      state: makeState(),
      isNovelaiV5Active: false,
    });
    expect(selfhost).toEqual(
      new Set([
        "novelaiImageModelNsfw",
        "novelaiImageModelSfw",
        "novelaiUsage",
        "surroundingsPeople",
        "novelaiTextModel",
      ]),
    );

    const novelaiTier3 = getUnavailableItemIds({
      state: makeState({
        imageProvider: "novelai",
        novelaiTier: 3,
        enableSurroundingsImage: true,
      }),
      isNovelaiV5Active: false,
    });
    expect(novelaiTier3).toEqual(new Set(["novelaiUsage"]));
  });
});

describe("countMatchesByCategory", () => {
  it("カテゴリごとの一致件数を数える", () => {
    const counts = countMatchesByCategory(
      new Set<SettingsItemId>(["difficulty", "nsfwMode", "fontFamily"]),
    );
    expect(counts.get("game")).toBe(2);
    expect(counts.get("display")).toBe(1);
    expect(counts.has("image")).toBe(false);
  });
});

describe("getItemIdsIn", () => {
  it("従来の画面では、実験的機能のセクションに今までどおりの順で並べる", () => {
    expect(getItemIdsIn("experimental", "classic")).toEqual([
      "promptExpander",
      "characterChat",
      "characterChatRealWorld",
      "surroundings",
      "surroundingsPeople",
      "clothingColor",
      "respectClothingLayers",
      "historyLookbackCount",
      "historyLookbackTargets",
      "enableMultiplePeople",
      "novelaiTextModel",
      "linkChatToImage",
      "playMemory",
    ]);
  });

  it("新しい画面では、役割に合うカテゴリへ移す", () => {
    expect(getItemIdsIn("experimental", "v2")).toEqual([
      "promptExpander",
      "characterChat",
      "characterChatRealWorld",
      "playMemory",
    ]);
    expect(getItemIdsIn("image", "v2")).toEqual([
      "imageProvider",
      "novelaiImageModelNsfw",
      "novelaiImageModelSfw",
      "novelaiUsage",
      "surroundings",
      "surroundingsPeople",
      "clothingColor",
      "respectClothingLayers",
      "enableMultiplePeople",
    ]);
    expect(getItemIdsIn("game", "v2").slice(-3)).toEqual([
      "historyLookbackCount",
      "historyLookbackTargets",
      "novelaiTextModel",
    ]);
    expect(getItemIdsIn("display", "v2")).toEqual([
      "fontFamily",
      "confirmFavoriteRemove",
      "linkChatToImage",
    ]);
  });

  it("どちらの画面でも、すべての項目をちょうど1回ずつ並べる", () => {
    for (const layout of ["classic", "v2"] as const) {
      const ids = SETTINGS_CATEGORIES.flatMap((category) =>
        getItemIdsIn(category.id, layout),
      );
      expect([...ids].sort()).toEqual(
        SETTINGS_ITEMS.map((item) => item.id).sort(),
      );
    }
  });
});

describe("移した項目の検索", () => {
  it("新しいカテゴリの見出しで一致する", () => {
    const matched = findMatchingItemIds(
      tJa("settings.imageSection"),
      jaTexts,
      noneUnavailable,
    );
    expect(matched?.has("clothingColor")).toBe(true);
    expect(matched?.has("enableMultiplePeople")).toBe(true);
  });
});
