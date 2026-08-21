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
