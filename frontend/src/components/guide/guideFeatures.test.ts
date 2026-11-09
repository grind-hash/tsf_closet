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
      available: false,
    });
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
