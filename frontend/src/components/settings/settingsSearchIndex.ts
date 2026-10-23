/**
 * 設定画面の検索索引。
 *
 * 新しい設定画面（左ナビ＋検索）で、カテゴリの並びと各項目の検索対象文言を1か所で持つ。
 * 項目 ID は SettingsScreen.tsx の SettingsItem と対応させる。
 */

import type { SettingsState } from "../../contexts/SettingsContext";
import type { TranslationKey } from "../../i18n";

/** 既存セクションの並び順をそのままカテゴリにする */
export const SETTINGS_CATEGORIES = [
  { id: "game", titleKey: "settings.gameSection" },
  { id: "adventure", titleKey: "settings.adventureSection" },
  { id: "display", titleKey: "settings.displaySection" },
  { id: "image", titleKey: "settings.imageSection" },
  { id: "selfProfile", titleKey: "settings.selfProfile.sectionTitle" },
  { id: "memory", titleKey: "settings.memory.sectionTitle" },
  { id: "speech", titleKey: "settings.speech.sectionTitle" },
  { id: "notify", titleKey: "settings.notifySection" },
  { id: "experimental", titleKey: "settings.experimentalSection" },
  { id: "avatar", titleKey: "settings.avatar.sectionTitle" },
  { id: "live2d", titleKey: "settings.live2d.sectionTitle" },
  { id: "data", titleKey: "settings.dataSection" },
] as const satisfies ReadonlyArray<{ id: string; titleKey: TranslationKey }>;

export type SettingsCategoryId = (typeof SETTINGS_CATEGORIES)[number]["id"];

export function isSettingsCategoryId(
  value: string,
): value is SettingsCategoryId {
  return SETTINGS_CATEGORIES.some((category) => category.id === value);
}

/** 表示可否の判定に使う値 */
export interface SettingsAvailabilityInput {
  state: SettingsState;
  isNovelaiV5Active: boolean;
}

interface SettingsItemDefinition {
  id: string;
  /** 新しい設定画面で置くカテゴリ */
  category: SettingsCategoryId;
  /** 従来の画面で置くセクション。category と同じなら省略する */
  section?: SettingsCategoryId;
  /** ラベル・説明・選択肢など、検索対象にする文言のキー */
  searchKeys: readonly TranslationKey[];
  /** 表示言語によらない検索語（製品名・略語など） */
  keywords?: readonly string[];
  /** 現在の設定・環境で表示する項目か。未指定なら常に表示する */
  available?: (input: SettingsAvailabilityInput) => boolean;
}

const isNovelai = ({ state }: SettingsAvailabilityInput) =>
  state.imageProvider === "novelai";

export const SETTINGS_ITEMS = [
  // ゲーム設定
  {
    id: "difficulty",
    category: "game",
    searchKeys: [
      "settings.difficulty",
      "settings.easy",
      "settings.normal",
      "settings.hard",
    ],
  },
  {
    id: "bloomCalcMethod",
    category: "game",
    searchKeys: [
      "settings.bloomCalcMethod",
      "settings.bloomCalcMethodDesc",
      "settings.bloomCalcLegacy",
      "settings.bloomCalcNew",
    ],
  },
  {
    id: "feelingMode",
    category: "game",
    searchKeys: [
      "settings.feelingMode",
      "settings.feelingModeDesc",
      "settings.feelingModeLegacy",
      "settings.feelingModeGenderAware",
    ],
  },
  {
    id: "genderCongruenceLlm",
    category: "game",
    searchKeys: [
      "settings.genderCongruenceLlm",
      "settings.genderCongruenceLlmDesc",
    ],
  },
  {
    id: "nsfwMode",
    category: "game",
    searchKeys: ["settings.nsfwMode", "settings.nsfwDesc"],
  },
  {
    id: "language",
    category: "game",
    searchKeys: ["settings.language", "settings.ja", "settings.en"],
    keywords: ["Language", "言語"],
  },

  // TSFシナリオ
  {
    id: "adventureEnabled",
    category: "adventure",
    searchKeys: ["settings.adventureEnabled", "settings.adventureEnabledDesc"],
  },
  {
    id: "adventureCompositeScene",
    category: "adventure",
    searchKeys: [
      "settings.adventureEnableCompositeScene",
      "settings.adventureEnableCompositeSceneDesc",
    ],
  },

  // 表示設定
  {
    id: "fontFamily",
    category: "display",
    searchKeys: [
      "settings.fontFamily",
      "settings.fontFamilyDesc",
      "settings.fontSystem",
      "settings.fontBrowserDefault",
    ],
    keywords: [
      "Noto Sans JP",
      "BIZ UDGothic",
      "BIZ UDMincho",
      "Inter",
      "Roboto Mono",
    ],
  },
  {
    id: "confirmFavoriteRemove",
    category: "display",
    searchKeys: [
      "settings.confirmFavoriteRemove",
      "settings.confirmFavoriteRemoveDesc",
    ],
  },

  // 画像生成
  {
    id: "imageProvider",
    category: "image",
    searchKeys: [
      "settings.imageProvider",
      "settings.providerReadonly",
      "settings.selfhost",
      "settings.openrouter",
      "settings.novelai",
    ],
  },
  {
    id: "novelaiImageModelNsfw",
    category: "image",
    searchKeys: [
      "settings.novelaiImageModelNsfw",
      "settings.novelaiImageModelNsfwDesc",
    ],
    keywords: ["NovelAI"],
    available: isNovelai,
  },
  {
    id: "novelaiImageModelSfw",
    category: "image",
    searchKeys: [
      "settings.novelaiImageModelSfw",
      "settings.novelaiImageModelSfwDesc",
    ],
    keywords: ["NovelAI"],
    available: isNovelai,
  },
  {
    id: "novelaiUsage",
    category: "image",
    searchKeys: ["settings.novelaiUsageTitle", "settings.novelaiUsageDesc"],
    keywords: ["NovelAI", "Anlas"],
    available: (input) =>
      isNovelai(input) &&
      input.isNovelaiV5Active &&
      Boolean(input.state.anlasBalance?.usage),
  },

  // 自分自身モード キャラ設定（ブロック単位）
  {
    id: "selfProfile",
    category: "selfProfile",
    searchKeys: [
      "settings.selfProfile.inputLabel",
      "settings.selfProfile.currentProfile",
      "settings.selfProfile.displayName",
      "settings.selfProfile.personality",
      "settings.selfProfile.reactionStyle",
      "settings.selfProfile.pronoun",
      "settings.selfProfile.gender",
      "settings.selfProfile.interests",
      "settings.selfProfile.tsfAttitude",
    ],
  },

  // メモリ（ブロック単位）
  {
    id: "memory",
    category: "memory",
    searchKeys: [
      "settings.memory.description",
      "settings.memory.sessionCountLabel",
      "settings.memory.regenerateLabel",
      "settings.memory.generateButton",
      "settings.memory.textAreaLabel",
    ],
  },

  // 音声合成（ブロック単位）
  {
    id: "speech",
    category: "speech",
    searchKeys: [
      "settings.speech.section1Title",
      "settings.speech.section2Title",
      "settings.speech.section3Title",
      "settings.speech.enable",
      "settings.speech.enableDesc",
      "settings.speech.enginePort",
      "settings.speech.useGpu",
      "settings.speech.engineDir",
      "settings.speech.downloadModel",
      "settings.speech.fetchSpeakers",
      "settings.speech.speaker",
      "settings.speech.style",
      "settings.speech.outputFormat",
    ],
    keywords: ["TTS", "AivisSpeech"],
  },

  // 通知設定
  {
    id: "achievementNotify",
    category: "notify",
    searchKeys: [
      "settings.achievementNotify",
      "settings.achievementNotifyDesc",
    ],
  },
  {
    id: "realityAttributeNotify",
    category: "notify",
    searchKeys: [
      "settings.realityAttributeNotify",
      "settings.realityAttributeNotifyDesc",
    ],
  },

  // 実験的機能（新しい設定画面では、役割に合うカテゴリへ移す項目を含む）
  {
    id: "promptExpander",
    category: "experimental",
    searchKeys: [
      "settings.experimentalPromptExpander",
      "settings.experimentalPromptExpanderDesc",
    ],
  },
  {
    id: "characterChat",
    category: "experimental",
    searchKeys: [
      "settings.experimentalCharacterChat",
      "settings.experimentalCharacterChatDesc",
    ],
  },
  {
    id: "characterChatRealWorld",
    category: "experimental",
    searchKeys: [
      "settings.characterChatWebSearch",
      "settings.characterChatWebSearchDesc",
      "settings.characterChatWeather",
      "settings.characterChatWeatherDesc",
    ],
  },
  {
    id: "surroundings",
    category: "image",
    section: "experimental",
    searchKeys: [
      "settings.experimentalSurroundings",
      "settings.experimentalSurroundingsDesc",
    ],
  },
  {
    id: "surroundingsPeople",
    category: "image",
    section: "experimental",
    searchKeys: [
      "settings.experimentalSurroundingsPeople",
      "settings.experimentalSurroundingsPeopleDesc",
    ],
    available: ({ state }) => state.enableSurroundingsImage,
  },
  {
    id: "clothingColor",
    category: "image",
    section: "experimental",
    searchKeys: [
      "settings.experimentalClothingColor",
      "settings.experimentalClothingColorDesc",
    ],
  },
  {
    id: "respectClothingLayers",
    category: "image",
    section: "experimental",
    searchKeys: [
      "settings.respectClothingLayers",
      "settings.respectClothingLayersDesc",
    ],
  },
  {
    id: "historyLookbackCount",
    category: "game",
    section: "experimental",
    searchKeys: [
      "settings.historyLookbackCount",
      "settings.historyLookbackCountDesc",
    ],
  },
  {
    id: "historyLookbackTargets",
    category: "game",
    section: "experimental",
    searchKeys: [
      "settings.historyLookbackTargets",
      "settings.historyLookbackTargetsDesc",
      "settings.historyLookbackTargetAction",
      "settings.historyLookbackTargetConversation",
      "settings.historyLookbackTargetDressUp",
      "settings.historyLookbackTargetRealityAlter",
    ],
  },
  {
    id: "enableMultiplePeople",
    category: "image",
    section: "experimental",
    searchKeys: [
      "settings.enableMultiplePeople",
      "settings.enableMultiplePeopleDesc",
    ],
  },
  {
    id: "novelaiTextModel",
    category: "game",
    section: "experimental",
    searchKeys: [
      "settings.novelaiTextModel",
      "settings.novelaiTextModelDesc",
      "settings.novelaiTextModelGlm",
      "settings.novelaiTextModelXialong",
    ],
    keywords: ["NovelAI"],
    available: (input) => isNovelai(input) && input.state.novelaiTier === 3,
  },
  {
    id: "linkChatToImage",
    category: "display",
    section: "experimental",
    searchKeys: ["settings.linkChatToImage", "settings.linkChatToImageDesc"],
  },
  {
    id: "playMemory",
    category: "experimental",
    searchKeys: [
      "settings.experimentalPlayMemory",
      "settings.experimentalPlayMemoryDesc",
    ],
  },

  // 3Dモデル（ブロック単位）
  {
    id: "avatarModels",
    category: "avatar",
    searchKeys: [
      "settings.avatar.description",
      "settings.avatar.dropZone",
      "settings.avatar.autoClassify",
    ],
    keywords: ["VRM", "3D"],
  },

  // Live2D（ブロック単位）
  {
    id: "live2d",
    category: "live2d",
    searchKeys: ["settings.live2d.description", "settings.live2d.guideTitle"],
    keywords: ["Live2D", "Cubism"],
  },

  // データ
  {
    id: "reset",
    category: "data",
    searchKeys: ["settings.reset", "settings.resetDesc"],
  },
] as const satisfies readonly SettingsItemDefinition[];

export type SettingsItemId = (typeof SETTINGS_ITEMS)[number]["id"];

const ITEM_DEFINITIONS: readonly SettingsItemDefinition[] = SETTINGS_ITEMS;

export type SettingsLayout = "classic" | "v2";

function groupItemIds(
  pick: (item: SettingsItemDefinition) => SettingsCategoryId,
): ReadonlyMap<SettingsCategoryId, readonly SettingsItemId[]> {
  const groups = new Map<SettingsCategoryId, SettingsItemId[]>();
  for (const item of ITEM_DEFINITIONS) {
    const key = pick(item);
    const ids = groups.get(key) ?? [];
    ids.push(item.id as SettingsItemId);
    groups.set(key, ids);
  }
  return groups;
}

const ITEM_IDS_BY_LAYOUT: Record<
  SettingsLayout,
  ReadonlyMap<SettingsCategoryId, readonly SettingsItemId[]>
> = {
  classic: groupItemIds((item) => item.section ?? item.category),
  v2: groupItemIds((item) => item.category),
};

/** セクション（カテゴリ）に並べる項目 ID。並び順は SETTINGS_ITEMS の順 */
export function getItemIdsIn(
  category: SettingsCategoryId,
  layout: SettingsLayout,
): readonly SettingsItemId[] {
  return ITEM_IDS_BY_LAYOUT[layout].get(category) ?? [];
}

/**
 * 全角/半角・大文字/小文字・カタカナ/ひらがなの違いをそろえる。
 * 空白はそのまま残す（ハイライトで元の文字位置へ戻すため）。
 */
export function foldSearchChars(text: string): string {
  return text
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[ァ-ヶ]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0x60));
}

/** 検索用に文字列をそろえる（foldSearchChars に加えて空白をまとめる） */
export function normalizeSearchText(text: string): string {
  return foldSearchChars(text).replace(/\s+/g, " ").trim();
}

/** クエリを検索語に分ける */
export function toSearchTerms(query: string): string[] {
  return normalizeSearchText(query).split(" ").filter(Boolean);
}

/** 現在の設定・環境では表示しない項目 */
export function getUnavailableItemIds(
  input: SettingsAvailabilityInput,
): Set<SettingsItemId> {
  const ids = new Set<SettingsItemId>();
  for (const item of ITEM_DEFINITIONS) {
    if (item.available && !item.available(input)) {
      ids.add(item.id as SettingsItemId);
    }
  }
  return ids;
}

/** 項目ごとの検索対象文字列（正規化済み）。表示言語が変わったら作り直す */
export function buildSearchTexts(
  translate: (key: TranslationKey) => string,
): ReadonlyMap<SettingsItemId, string> {
  const categoryTitles = new Map<SettingsCategoryId, string>(
    SETTINGS_CATEGORIES.map((category) => [
      category.id,
      translate(category.titleKey),
    ]),
  );
  const texts = new Map<SettingsItemId, string>();
  for (const item of ITEM_DEFINITIONS) {
    const parts = [
      categoryTitles.get(item.category) ?? "",
      ...item.searchKeys.map((key) => translate(key)),
      ...(item.keywords ?? []),
    ];
    texts.set(item.id as SettingsItemId, normalizeSearchText(parts.join(" ")));
  }
  return texts;
}

/**
 * クエリの語をすべて含む項目を返す（空白区切りの AND 検索）。
 * クエリが空なら null（検索していない）を返す。
 */
export function findMatchingItemIds(
  query: string,
  searchTexts: ReadonlyMap<SettingsItemId, string>,
  unavailableIds: ReadonlySet<SettingsItemId>,
): Set<SettingsItemId> | null {
  const terms = toSearchTerms(query);
  if (terms.length === 0) return null;
  const matched = new Set<SettingsItemId>();
  for (const [id, text] of searchTexts) {
    if (unavailableIds.has(id)) continue;
    if (terms.every((term) => text.includes(term))) {
      matched.add(id);
    }
  }
  return matched;
}

/** カテゴリごとの一致件数 */
export function countMatchesByCategory(
  matchedIds: ReadonlySet<SettingsItemId>,
): Map<SettingsCategoryId, number> {
  const counts = new Map<SettingsCategoryId, number>();
  for (const item of SETTINGS_ITEMS) {
    if (matchedIds.has(item.id)) {
      counts.set(item.category, (counts.get(item.category) ?? 0) + 1);
    }
  }
  return counts;
}
