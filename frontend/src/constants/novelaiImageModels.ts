// NovelAI 画像生成モデルの選択肢（バックエンド consts/novelai_models.py のミラー）

// NSFW ON 時に選択可能なモデル
export const NSFW_IMAGE_MODEL_OPTIONS = [
  "nai-diffusion-4-5-full",
  "nai-diffusion-5-full",
  "nai-diffusion-5-full-medium",
] as const;

// NSFW OFF 時に選択可能なモデル
export const SFW_IMAGE_MODEL_OPTIONS = [
  "nai-diffusion-4-5-curated",
  "nai-diffusion-5-curated",
] as const;

export const DEFAULT_NSFW_IMAGE_MODEL = "nai-diffusion-4-5-full";
export const DEFAULT_SFW_IMAGE_MODEL = "nai-diffusion-4-5-curated";

const V5_IMAGE_MODELS = new Set<string>([
  "nai-diffusion-5-full",
  "nai-diffusion-5-full-medium",
  "nai-diffusion-5-curated",
]);

// 節約モード（NovelAI の Medium effort）のモデル。steps 固定で独自ネガティブを受け付けない
const ECONOMY_IMAGE_MODELS = new Set<string>(["nai-diffusion-5-full-medium"]);

/** モデル名が V5 系かどうかを返す（未知名・空は false） */
export function isV5ImageModel(name: string | null | undefined): boolean {
  return name ? V5_IMAGE_MODELS.has(name) : false;
}

/** モデル名が節約モードかどうかを返す（未知名・空は false） */
export function isEconomyImageModel(name: string | null | undefined): boolean {
  return name ? ECONOMY_IMAGE_MODELS.has(name) : false;
}

/**
 * 精密参照の送信形式。"v4_5" は忠実度あり・強度 1.0 まで、"v5" は衣装参照あり・
 * 強度 5.0 まで・忠実度なし。バックエンド NovelAIImageModelInfo.precise_reference_format のミラー
 */
export type PreciseReferenceFormat = "v4_5" | "v5";

const V5_PRECISE_REFERENCE_MODELS = new Set<string>([
  "nai-diffusion-5-full",
  "nai-diffusion-5-curated",
]);

/**
 * モデル名から精密参照の送信形式を返す。節約モードは精密参照に非対応のため null。
 * 未知名・空は v4.5 相当として "v4_5"（バックエンドと同じ扱い）
 */
export function preciseReferenceFormat(
  name: string | null | undefined,
): PreciseReferenceFormat | null {
  if (!name) return "v4_5";
  if (ECONOMY_IMAGE_MODELS.has(name)) return null;
  return V5_PRECISE_REFERENCE_MODELS.has(name) ? "v5" : "v4_5";
}

/** NSFW 設定から実際に使われる NovelAI 画像モデルを返す（Full 側 / Curated 側） */
export function resolveEffectiveNovelaiImageModel({
  nsfwMode,
  novelaiImageModel,
  novelaiCuratedImageModel,
}: {
  nsfwMode: boolean;
  novelaiImageModel: string;
  novelaiCuratedImageModel: string;
}): string {
  return nsfwMode ? novelaiImageModel : novelaiCuratedImageModel;
}

// V5 利用上限使い切り警告の抑止キー（ブラウザセッション単位、sessionStorage）。
// 通常ゲーム / TSFシナリオ / Prompt Expander で共有する
export const V5_USAGE_WARN_SUPPRESSED_KEY = "v5_usage_warn_suppressed";

// TSFシナリオ(Adventure)の run 単位モデル上書きで選べる全モデルと表示名。
// NSFW 設定に依らず4モデルすべてを提示する（Curated は非NSFW向け）
export const ADVENTURE_IMAGE_MODEL_CHOICES: ReadonlyArray<{
  value: string;
  label: string;
}> = [
  { value: "nai-diffusion-4-5-full", label: "NAI Diffusion V4.5 Full" },
  { value: "nai-diffusion-4-5-curated", label: "NAI Diffusion V4.5 Curated" },
  { value: "nai-diffusion-5-full", label: "NAI Diffusion V5 Full" },
  {
    value: "nai-diffusion-5-full-medium",
    label: "NAI Diffusion V5 Full (Medium effort)",
  },
  { value: "nai-diffusion-5-curated", label: "NAI Diffusion V5 Curated" },
];

const ADVENTURE_IMAGE_MODEL_VALUES = new Set(
  ADVENTURE_IMAGE_MODEL_CHOICES.map((choice) => choice.value),
);

/** run 単位上書きとして有効なモデル名か（"default" や未知名は false） */
export function isAdventureImageModelValue(
  value: string | null | undefined,
): boolean {
  return value ? ADVENTURE_IMAGE_MODEL_VALUES.has(value) : false;
}
