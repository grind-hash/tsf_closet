/**
 * 遊び方ガイドの項目一覧
 *
 * 機能の説明はガイドの文面(i18n の guide.<key>)を唯一の情報源にする。案内役のセレナにも
 * buildSerenaAppGuide で同じ文面を発言ごとに渡す。メニュー項目や機能フラグを足したら
 * ここにも足すこと(足し忘れると guideFeatures.test.ts が落ちる)。
 *
 * desc と note はカードにそのまま出るので短く保ち、長い機能の細かい仕様は details
 * (「くわしく見る」の見出しごとの箇条書き)に書く。どれもバックエンドの受け取りに長さの上限が
 * あり、超えるとセレナへの送信が弾かれる(上限は guideFeatures.test.ts で確かめる)。
 */
import type { TFunction } from "i18next";
import type { AppGuideDetail, AppGuideFeature } from "../../apis/characterChat";
import type { SettingsState } from "../../contexts/SettingsContext";
import type { guide as jaGuide } from "../../i18n/ja/guide";

type GuideTexts = typeof jaGuide;

/** ガイドの i18n のうち、タイトルと説明を持つ項目のキー */
export type GuideEntryKey = {
  [K in keyof GuideTexts]: GuideTexts[K] extends { title: string; desc: string }
    ? K
    : never;
}[keyof GuideTexts];

/** ガイドの1項目の文面。details は「くわしく見る」で開く細かい仕様(長い機能だけ) */
export interface GuideEntryText {
  title: string;
  desc: string;
  note?: string;
  details?: readonly AppGuideDetail[];
}

export interface GuideFeature {
  key: GuideEntryKey;
  /** basics = 基本の画面(切り替え無し) / features = ONにして広げる遊び方 */
  section: "basics" | "features";
  icon: string;
  /** この項目が説明するサイドメニューの項目 id */
  menuIds: readonly string[];
  /** すべて true のとき使える。空なら切り替えの無い機能 */
  settingKeys: readonly (keyof SettingsState)[];
}

export const GUIDE_FEATURES: readonly GuideFeature[] = [
  {
    key: "newGame",
    section: "basics",
    icon: "🎮",
    menuIds: ["new-game"],
    settingKeys: [],
  },
  {
    key: "gallery",
    section: "basics",
    icon: "🖼️",
    menuIds: ["gallery"],
    settingKeys: [],
  },
  {
    key: "characters",
    section: "basics",
    icon: "👤",
    menuIds: ["characters"],
    settingKeys: [],
  },
  {
    key: "records",
    section: "basics",
    icon: "🏆",
    menuIds: ["endings", "achievements"],
    settingKeys: [],
  },
  {
    key: "settings",
    section: "basics",
    icon: "⚙️",
    menuIds: ["settings"],
    settingKeys: [],
  },
  {
    key: "adventure",
    section: "features",
    icon: "📖",
    menuIds: ["adventure", "bgm-test"],
    settingKeys: ["adventureEnabled"],
  },
  {
    key: "talk",
    section: "features",
    icon: "🗨️",
    menuIds: [],
    settingKeys: ["adventureEnabled", "characterChatEnabled"],
  },
  {
    key: "inventory",
    section: "features",
    icon: "🎒",
    menuIds: [],
    settingKeys: ["adventureEnabled"],
  },
  {
    key: "vrm",
    section: "features",
    icon: "🧍",
    menuIds: [],
    settingKeys: [],
  },
  {
    key: "promptExpander",
    section: "features",
    icon: "✨",
    menuIds: ["prompt-expander"],
    settingKeys: ["experimentalPromptExpanderEnabled"],
  },
  {
    key: "characterChat",
    section: "features",
    icon: "💬",
    menuIds: ["character-chat"],
    settingKeys: ["characterChatEnabled"],
  },
  {
    key: "salon",
    section: "features",
    icon: "🪞",
    menuIds: ["salon"],
    settingKeys: ["experimentalSalonEnabled"],
  },
  {
    key: "hakoniwa",
    // 世界ごとのWeb検索設定(既定OFF)とAI発言の注記・出典も、detailsからセレナへ渡す
    section: "features",
    icon: "🏠",
    menuIds: ["hakoniwa"],
    settingKeys: ["experimentalHakoniwaEnabled"],
  },
  {
    key: "voice",
    section: "features",
    icon: "🔊",
    menuIds: [],
    settingKeys: ["ttsEnabled"],
  },
  {
    key: "playMemory",
    section: "features",
    icon: "📝",
    menuIds: [],
    settingKeys: ["playMemoryEnabled"],
  },
];

/** ガイドの項目が要らないメニュー項目と、その理由 */
export const GUIDE_EXEMPT_MENU_IDS: Readonly<Record<string, string>> = {
  guide: "遊び方ガイド自身",
};

/** ガイドの項目が要らない *Enabled の設定と、その理由(遊び方の有無を変えない設定) */
export const GUIDE_EXEMPT_SETTING_KEYS: Readonly<
  Partial<Record<keyof SettingsState, string>>
> = {
  genderCongruenceLlmEnabled: "通常プレイの生成方式の調整",
  inpaintEnabled: "通常プレイの画像編集の一時的な状態",
  characterChatWebSearchEnabled:
    "セレナの調べ物の任意設定。characterChat の注記で説明する",
  characterChatWeatherEnabled:
    "セレナの調べ物の任意設定。characterChat の注記で説明する",
  playMemorySystemEnabled: "プレイメモの内訳の切り替え",
  playMemoryUserEnabled: "プレイメモの内訳の切り替え",
  newSettingsScreenEnabled: "設定画面のレイアウトの切り替え",
  soundEnabled: "音の設定で、遊び方の追加ではない",
  multiCharacterPanelEnabled: "通常プレイの右パネルの表示切り替え",
};

export function guideIcon(key: GuideEntryKey): string {
  return GUIDE_FEATURES.find((feature) => feature.key === key)?.icon ?? "";
}

/** セレナに渡す機能一覧を、ガイドの文面といまの設定から組み立てる */
export function buildSerenaAppGuide(
  t: TFunction,
  settings: SettingsState,
): AppGuideFeature[] {
  const texts = t("guide", { returnObjects: true }) as GuideTexts;
  return GUIDE_FEATURES.map((feature) => {
    const entry: GuideEntryText = texts[feature.key];
    return {
      id: feature.key,
      title: entry.title,
      desc: entry.desc,
      note: entry.note ?? null,
      details: (entry.details ?? []).map((section) => ({
        heading: section.heading,
        items: [...section.items],
      })),
      available:
        feature.settingKeys.length === 0
          ? null
          : feature.settingKeys.every((key) => settings[key] === true),
    };
  });
}
