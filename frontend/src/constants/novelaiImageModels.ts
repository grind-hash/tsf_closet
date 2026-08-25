// NovelAI 画像生成モデルの選択肢（バックエンド consts/novelai_models.py のミラー）

// NSFW ON 時に選択可能なモデル
export const NSFW_IMAGE_MODEL_OPTIONS = [
  "nai-diffusion-4-5-full",
  "nai-diffusion-5-full",
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
  "nai-diffusion-5-curated",
]);

/** モデル名が V5 系かどうかを返す（未知名・空は false） */
export function isV5ImageModel(name: string | null | undefined): boolean {
  return name ? V5_IMAGE_MODELS.has(name) : false;
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
