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
