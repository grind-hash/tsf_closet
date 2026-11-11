/**
 * 遊び方ガイドの書き忘れ検出。
 *
 * メニュー項目・機能フラグ・ガイドの文面がそろっていないと落ちる。ガイドの文面は
 * 案内役のセレナの機能知識も兼ねるため、ここが通っていればセレナも新機能を知っている。
 */
import type { TFunction } from "i18next";
import { describe, expect, it } from "vitest";
import {
  defaultState,
  type SettingsState,
} from "../../contexts/SettingsContext";
import i18n from "../../i18n";
import { guide as enGuide } from "../../i18n/en/guide";
import { guide as jaGuide } from "../../i18n/ja/guide";
import { getMenuItems } from "../layout/SideMenu";
import {
  buildSerenaAppGuide,
  GUIDE_EXEMPT_MENU_IDS,
  GUIDE_EXEMPT_SETTING_KEYS,
  GUIDE_FEATURES,
} from "./guideFeatures";

const keyAsLabel = ((key: string) => key) as unknown as TFunction;

describe("遊び方ガイドの網羅", () => {
  it("サイドメニューのすべての項目に、ガイドの項目がある", () => {
    const menuIds = getMenuItems(keyAsLabel, true, true, true, true, true).map(
      (item) => item.id,
    );
    const covered = new Set([
      ...GUIDE_FEATURES.flatMap((feature) => feature.menuIds),
      ...Object.keys(GUIDE_EXEMPT_MENU_IDS),
    ]);
    const missing = menuIds.filter((id) => !covered.has(id));
    expect(
      missing,
      "メニュー項目を足したら guideFeatures.ts と i18n の guide に説明を書くこと",
    ).toEqual([]);
  });

  it("すべての *Enabled 設定が、ガイドの項目か理由付きの除外に入っている", () => {
    const flags = Object.entries(defaultState)
      .filter(
        ([key, value]) => key.endsWith("Enabled") && typeof value === "boolean",
      )
      .map(([key]) => key);
    const covered = new Set<string>([
      ...GUIDE_FEATURES.flatMap((feature) => feature.settingKeys),
      ...Object.keys(GUIDE_EXEMPT_SETTING_KEYS),
    ]);
    const missing = flags.filter((key) => !covered.has(key));
    expect(
      missing,
      "機能フラグを足したら guideFeatures.ts の settingKeys か除外(理由付き)に入れること",
    ).toEqual([]);
  });

  it("ガイドの i18n の項目と一覧が過不足なく一致する", () => {
    const i18nKeys = Object.entries(jaGuide)
      .filter(
        ([, value]) =>
          typeof value === "object" && "title" in value && "desc" in value,
      )
      .map(([key]) => key)
      .sort();
    const registryKeys = GUIDE_FEATURES.map((feature) => feature.key).sort();
    expect(registryKeys).toEqual(i18nKeys);
  });

  it("menuIds と settingKeys は実在する値だけを指す", () => {
    const menuIds = new Set(
      getMenuItems(keyAsLabel, true, true, true, true, true).map(
        (item) => item.id,
      ),
    );
    for (const feature of GUIDE_FEATURES) {
      for (const id of feature.menuIds) expect(menuIds).toContain(id);
      for (const key of feature.settingKeys)
        expect(typeof defaultState[key]).toBe("boolean");
    }
  });
});

describe("buildSerenaAppGuide", () => {
  const tJa = i18n.getFixedT("ja") as unknown as TFunction;
  const tEn = i18n.getFixedT("en") as unknown as TFunction;

  function state(overrides: Partial<SettingsState> = {}): SettingsState {
    return { ...defaultState, ...overrides };
  }

  it("ガイドの文面をそのまま渡し、無効な機能は available: false になる", () => {
    const features = buildSerenaAppGuide(
      tJa,
      state({ experimentalSalonEnabled: false }),
    );
    const salon = features.find((feature) => feature.id === "salon");
    expect(salon).toEqual({
      id: "salon",
      title: jaGuide.salon.title,
      desc: jaGuide.salon.desc,
      note: jaGuide.salon.note,
      details: jaGuide.salon.details.map((section) => ({
        heading: section.heading,
        items: [...section.items],
      })),
      available: false,
    });
    // 細かい仕様の無い項目は空の配列で渡す
    expect(features.find((f) => f.id === "gallery")?.details).toEqual([]);
  });

  it("有効にすると available: true、基本の画面は切り替えが無いので null", () => {
    const features = buildSerenaAppGuide(
      tJa,
      state({ experimentalSalonEnabled: true }),
    );
    expect(features.find((f) => f.id === "salon")?.available).toBe(true);
    expect(features.find((f) => f.id === "newGame")?.available).toBeNull();
    expect(features.find((f) => f.id === "gallery")?.note).toBeNull();
  });

  it("前提の機能が OFF なら、子の機能も無効になる", () => {
    const features = buildSerenaAppGuide(
      tJa,
      state({ adventureEnabled: true, characterChatEnabled: false }),
    );
    expect(features.find((f) => f.id === "talk")?.available).toBe(false);
  });

  it("英語のガイドからも組める", () => {
    const features = buildSerenaAppGuide(tEn, state());
    expect(features.find((f) => f.id === "salon")?.title).toBe(
      "Salon Management",
    );
  });
});

/**
 * セレナへ送る遊び方ガイドの長さの上限。バックエンドの consts/character_chat.py の
 * APP_GUIDE_* と同じ値にする。超えると送信がまるごと弾かれ、セレナと話せなくなる
 * (2026-11 に AI箱庭の note が 1000 字を超えて実際に起きた)。
 */
const APP_GUIDE_TITLE_MAX = 80;
const APP_GUIDE_TEXT_MAX = 1000;
const APP_GUIDE_DETAIL_SECTIONS_MAX = 12;
const APP_GUIDE_DETAIL_ITEMS_MAX = 10;
const APP_GUIDE_DETAIL_ITEM_MAX = 400;

describe("セレナへ送るガイドの長さ", () => {
  for (const [lang, t] of [
    ["ja", i18n.getFixedT("ja")],
    ["en", i18n.getFixedT("en")],
  ] as const) {
    it(`${lang}: どの項目もバックエンドの上限に収まる`, () => {
      const features = buildSerenaAppGuide(
        t as unknown as TFunction,
        defaultState,
      );
      for (const feature of features) {
        const where = `${lang}/${feature.id}`;
        expect(feature.title.length, `${where} title`).toBeLessThanOrEqual(
          APP_GUIDE_TITLE_MAX,
        );
        expect(feature.desc.length, `${where} desc`).toBeLessThanOrEqual(
          APP_GUIDE_TEXT_MAX,
        );
        expect(feature.note?.length ?? 0, `${where} note`).toBeLessThanOrEqual(
          APP_GUIDE_TEXT_MAX,
        );
        expect(feature.details.length, `${where} details`).toBeLessThanOrEqual(
          APP_GUIDE_DETAIL_SECTIONS_MAX,
        );
        for (const section of feature.details) {
          expect(
            section.heading.length,
            `${where} ${section.heading}`,
          ).toBeLessThanOrEqual(APP_GUIDE_TITLE_MAX);
          expect(
            section.items.length,
            `${where} ${section.heading}`,
          ).toBeLessThanOrEqual(APP_GUIDE_DETAIL_ITEMS_MAX);
          for (const item of section.items) {
            expect(
              item.length,
              `${where} ${item.slice(0, 20)}`,
            ).toBeLessThanOrEqual(APP_GUIDE_DETAIL_ITEM_MAX);
          }
        }
      }
    });
  }

  it("日本語と英語で、くわしく見るの見出しの数がそろっている", () => {
    const sections = (entry: object) =>
      "details" in entry && Array.isArray(entry.details)
        ? entry.details.length
        : 0;
    for (const feature of GUIDE_FEATURES) {
      expect(sections(enGuide[feature.key]), feature.key).toBe(
        sections(jaGuide[feature.key]),
      );
    }
  });
});
