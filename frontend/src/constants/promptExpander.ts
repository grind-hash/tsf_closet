// Prompt Expander の定数（バックエンド consts/prompt_expander.py のミラー）

import { isV5ImageModel } from "./novelaiImageModels";

/** Prompt Expander で選択できる NovelAI 画像モデル（表示順） */
export const PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS = [
  "nai-diffusion-5-full",
  "nai-diffusion-5-curated",
  "nai-diffusion-4-5-full",
  "nai-diffusion-4-5-curated",
] as const;

export type PromptExpanderImageModel =
  (typeof PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS)[number];

export const DEFAULT_PROMPT_EXPANDER_IMAGE_MODEL: PromptExpanderImageModel =
  "nai-diffusion-4-5-full";

/** モデル選択肢の表示ラベル */
export const PROMPT_EXPANDER_IMAGE_MODEL_LABELS: Record<
  PromptExpanderImageModel,
  string
> = {
  "nai-diffusion-5-full": "NAI Diffusion V5 Full",
  "nai-diffusion-5-curated": "NAI Diffusion V5 Curated",
  "nai-diffusion-4-5-full": "NAI Diffusion V4.5 Full",
  "nai-diffusion-4-5-curated": "NAI Diffusion V4.5 Curated",
};

/** バッジ等で使う短いモデル表記 */
export const PROMPT_EXPANDER_IMAGE_MODEL_SHORT_LABELS: Record<
  PromptExpanderImageModel,
  string
> = {
  "nai-diffusion-5-full": "V5 Full",
  "nai-diffusion-5-curated": "V5 Curated",
  "nai-diffusion-4-5-full": "V4.5 Full",
  "nai-diffusion-4-5-curated": "V4.5 Curated",
};

/** キャラクタープロンプトの上限数（V5 系 / V4.5 系） */
export const MAX_CHARACTER_PROMPTS_V5 = 22;
export const MAX_CHARACTER_PROMPTS_V45 = 6;

/** 画像モデルごとのキャラクタープロンプト上限数を返す */
export function getMaxCharacterPrompts(
  model: string | null | undefined,
): number {
  return isV5ImageModel(model)
    ? MAX_CHARACTER_PROMPTS_V5
    : MAX_CHARACTER_PROMPTS_V45;
}

/** 画像サイズの選択肢 */
export const PROMPT_EXPANDER_IMAGE_SIZES = [
  "portrait",
  "landscape",
  "square",
] as const;

export type PromptExpanderImageSize =
  (typeof PROMPT_EXPANDER_IMAGE_SIZES)[number];

/** プロンプト拡張に使える NovelAI テキストモデル */
export const NOVELAI_TEXT_MODEL_OPTIONS = ["glm-4-6", "xialong-v1"] as const;

export type NovelaiTextModel = (typeof NOVELAI_TEXT_MODEL_OPTIONS)[number];

/** 拡張モード（日本語プロンプト / Danbooru タグ） */
export type PromptExpandMode = "japanese" | "tags";

/** 生成元画像の種別 */
export type PromptExpanderSourceKind = "none" | "history" | "entry" | "upload";

/** i2i 強度の入力範囲 */
export const PROMPT_EXPANDER_I2I_STRENGTH_MIN = 0.05;
export const PROMPT_EXPANDER_I2I_STRENGTH_MAX = 0.99;
/** i2i ノイズの入力範囲 */
export const PROMPT_EXPANDER_I2I_NOISE_MIN = 0;
export const PROMPT_EXPANDER_I2I_NOISE_MAX = 0.5;
/** シードの入力範囲 */
export const PROMPT_EXPANDER_SEED_MAX = 999999999;
/** PE ローカルメモリの最大文字数 */
export const PROMPT_EXPANDER_MEMORY_MAX_LENGTH = 10000;

/** 漫画モード: コマ数（0 = おまかせ） */
export const PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO = 0;
export const PROMPT_EXPANDER_MANGA_PANEL_COUNT_MIN = 1;
export const PROMPT_EXPANDER_MANGA_PANEL_COUNT_MAX = 6;
/** 漫画モード: コマ割り */
export const PROMPT_EXPANDER_MANGA_LAYOUTS = [
  "auto",
  "vertical",
  "horizontal",
  "grid",
] as const;
export type PromptExpanderMangaLayout =
  (typeof PROMPT_EXPANDER_MANGA_LAYOUTS)[number];
/** 漫画モード: セリフ・効果音の言語（auto = 指示文の言語に合わせる） */
export const PROMPT_EXPANDER_MANGA_TEXT_LANGUAGES = [
  "auto",
  "ja",
  "en",
] as const;
export type PromptExpanderMangaTextLanguage =
  (typeof PROMPT_EXPANDER_MANGA_TEXT_LANGUAGES)[number];
/** 漫画モード: 読み順（rtl = 日本式: 右上始まりで右→左・上→下、ltr = 西洋式） */
export const PROMPT_EXPANDER_MANGA_READING_DIRECTIONS = ["rtl", "ltr"] as const;
export type PromptExpanderMangaReadingDirection =
  (typeof PROMPT_EXPANDER_MANGA_READING_DIRECTIONS)[number];

/** 漫画モードを使える画像モデルか（V5 系のみ） */
export function supportsMangaMode(model: string | null | undefined): boolean {
  return isV5ImageModel(model);
}

/** 精密参照（NovelAI character reference）の種別 */
export const PROMPT_EXPANDER_REFERENCE_TYPES = [
  "character",
  "style",
  "character&style",
] as const;
export type PromptExpanderReferenceType =
  (typeof PROMPT_EXPANDER_REFERENCE_TYPES)[number];
/** 既定は Adventure の立ち絵生成と同じ（立ち絵差分では同一性の固定が目的） */
export const DEFAULT_PROMPT_EXPANDER_REFERENCE_TYPE: PromptExpanderReferenceType =
  "character";
export const DEFAULT_PROMPT_EXPANDER_REFERENCE_STRENGTH = 0.85;
export const DEFAULT_PROMPT_EXPANDER_REFERENCE_FIDELITY = 1;
/** 精密参照 1 枚あたりの Anlas 消費（設定応答の anlas_per_reference が無いときの既定） */
export const PROMPT_EXPANDER_ANLAS_PER_REFERENCE = 5;
/** 精密参照の Anlas 確認ダイアログを抑止する sessionStorage キー（ブラウザセッション単位） */
export const PROMPT_EXPANDER_ANLAS_WARN_SUPPRESSED_KEY =
  "prompt_expander_anlas_warn_suppressed";

/** 精密参照を使える画像モデルか（V4.5 系のみ。V5 は API 非対応） */
export function supportsPreciseReference(
  model: string | null | undefined,
): boolean {
  return (
    (PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS as readonly string[]).includes(
      model ?? "",
    ) && !isV5ImageModel(model)
  );
}

/**
 * 背景透過をプロンプト指示だけでネイティブに行えるモデルか（V5 系）。
 * V4.5 系は白背景で生成し、表示時にフロントで切り抜く。
 */
export function usesNativeTransparency(
  model: string | null | undefined,
): boolean {
  return isV5ImageModel(model);
}

/** 参照種別の i18n キー（"character&style" は "&" をキーに使えないため characterStyle に写す） */
export function referenceTypeI18nKey(
  type: PromptExpanderReferenceType | string,
): string {
  return type === "character&style" ? "characterStyle" : type;
}

/**
 * 背景透過タグの強調段数（V4.5 系のみ効く）。
 * NovelAI の {} 記法は 1 段ごとに重み 1.05 倍で、無強調だと白背景の指定が
 * 無視されて背景が描かれ、切り抜きが失敗することがあるため既定は 2 段。
 * V5 はネイティブ透過なので段数を指定しても効かない。
 */
export const PROMPT_EXPANDER_TRANSPARENT_EMPHASIS_LEVELS = [
  0, 1, 2, 3,
] as const;
export type PromptExpanderTransparentEmphasis =
  (typeof PROMPT_EXPANDER_TRANSPARENT_EMPHASIS_LEVELS)[number];
export const DEFAULT_PROMPT_EXPANDER_TRANSPARENT_EMPHASIS: PromptExpanderTransparentEmphasis = 2;

/**
 * 背景透過で送信プロンプトの末尾へ足されるタグ（backend consts のミラー）。
 * エントリの最終プロンプトには保存されないため、欄の下のプレビューで見せる。
 */
export const TRANSPARENT_BACKGROUND_TAGS_V5 = [
  "transparent background",
  "no shadow",
] as const;
export const TRANSPARENT_BACKGROUND_TAGS_V45 = [
  "simple background",
  "white background",
  "no shadow",
] as const;
export const TRANSPARENT_BACKGROUND_NEGATIVE_TAGS = [
  "multiple views",
  "reference sheet",
  "character sheet",
  "turnaround",
] as const;
/** 強調対象は背景そのものを決めるタグだけ（no shadow は素のまま） */
export const TRANSPARENT_BACKGROUND_EMPHASIZED_TAGS: ReadonlySet<string> =
  new Set(["simple background", "white background"]);

/** NovelAI の {} 記法でタグを強調する（level 0 は素通し） */
export function emphasizeTag(tag: string, level: number): string {
  return level <= 0 ? tag : "{".repeat(level) + tag + "}".repeat(level);
}

/** 背景透過で正プロンプトへ足すタグ。強調は V4.5 の背景タグにだけ効く */
export function transparentBackgroundTags(
  model: string | null | undefined,
  emphasis = 0,
): string[] {
  if (usesNativeTransparency(model)) return [...TRANSPARENT_BACKGROUND_TAGS_V5];
  const level = Math.max(0, emphasis);
  return TRANSPARENT_BACKGROUND_TAGS_V45.map((tag) =>
    TRANSPARENT_BACKGROUND_EMPHASIZED_TAGS.has(tag)
      ? emphasizeTag(tag, level)
      : tag,
  );
}

/** 重み記法や括弧を外して照合用の表記へ整える（backend の normalize_tag_for_match と同じ） */
export function normalizeTagForMatch(tag: string): string {
  return tag
    .toLowerCase()
    .replace(/\d+(?:\.\d+)?::/g, "")
    .replace(/::/g, " ")
    .replace(/[{}[\]()]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * プロンプトへ実際に追加されるタグだけを返す（backend の merge_tags と同じ判定）。
 * 既に同じタグが入力済みなら追加されないので、プレビューにも出さない。
 */
export function appendedTags(
  prompt: string,
  tags: readonly string[],
): string[] {
  const existing = new Set(
    prompt
      .split(",")
      .map((item) => normalizeTagForMatch(item))
      .filter((item) => item.length > 0),
  );
  return tags.filter((tag) => !existing.has(normalizeTagForMatch(tag)));
}

/** 強調段数のプレビュー表記（例: 2 -> "{{ }}"） */
export function transparentEmphasisSample(level: number): string {
  return level <= 0 ? "—" : `${"{".repeat(level)} ${"}".repeat(level)}`;
}

/**
 * インペイント（部分修正）。i2i 元をベース画像として、マスクで塗った領域だけ描き直す。
 * NovelAI はマスクを 1/8 解像度で扱うため、書き出しのグリッドもそれに合わせる
 * （固定値にすると landscape / square でマスクの縦横比が崩れる）。
 */
export const PROMPT_EXPANDER_MASK_GRID_DIVISOR = 8;
export const PROMPT_EXPANDER_BRUSH_SIZE_MIN = 4;
export const PROMPT_EXPANDER_BRUSH_SIZE_MAX = 96;
export const DEFAULT_PROMPT_EXPANDER_BRUSH_SIZE = 32;

/** V4.5 の白背景画像を切り抜くときの許容差（Adventure の立ち絵と同じ。生成画像の白はわずかに灰色に振れる） */
export const PROMPT_EXPANDER_ALPHA_OPTIONS = {
  threshold: 12,
  featherRadius: 1.8,
} as const;

/** 漫画モードで選べるコマ数の一覧（0 = おまかせ を先頭に） */
export function mangaPanelCountOptions(): number[] {
  const counts: number[] = [PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO];
  for (
    let n = PROMPT_EXPANDER_MANGA_PANEL_COUNT_MIN;
    n <= PROMPT_EXPANDER_MANGA_PANEL_COUNT_MAX;
    n += 1
  ) {
    counts.push(n);
  }
  return counts;
}

/** 画像モデル名から表示ラベルを返す（未知名はそのまま返す） */
export function getPromptExpanderImageModelLabel(model: string): string {
  return (
    PROMPT_EXPANDER_IMAGE_MODEL_LABELS[model as PromptExpanderImageModel] ??
    model
  );
}

/** 画像モデル名から短い表示ラベルを返す（未知名はそのまま返す） */
export function getPromptExpanderImageModelShortLabel(model: string): string {
  return (
    PROMPT_EXPANDER_IMAGE_MODEL_SHORT_LABELS[
      model as PromptExpanderImageModel
    ] ?? model
  );
}
