/**
 * NovelAI画像サイズバリデーター
 *
 * NovelAI Opusプランの無料サイズ定義と判定関数。
 * 009-custom-image-anlas-warning
 */

/**
 * NovelAI Opus プランの無料サイズ定義
 */
export const NOVELAI_FREE_SIZES = {
  portrait: { maxWidth: 832, maxHeight: 1216 },
  landscape: { maxWidth: 1216, maxHeight: 832 },
  square: { maxWidth: 1024, maxHeight: 1024 },
} as const;

/**
 * 画像がNovelAI Opusプランの無料サイズ内に収まるかを判定
 *
 * @param width - 画像の幅（px）
 * @param height - 画像の高さ（px）
 * @returns true: 無料サイズ内、false: カスタムサイズ（Anlas消費対象）
 */
export function isWithinNovelAIFreeSize(
  width: number,
  height: number,
): boolean {
  const { portrait, landscape, square } = NOVELAI_FREE_SIZES;

  // 縦型: 832 x 1216 以下
  if (width <= portrait.maxWidth && height <= portrait.maxHeight) return true;
  // 横型: 1216 x 832 以下
  if (width <= landscape.maxWidth && height <= landscape.maxHeight) return true;
  // 正方形: 1024 x 1024 以下
  if (width <= square.maxWidth && height <= square.maxHeight) return true;

  return false;
}

/**
 * File オブジェクトから画像のサイズを取得
 *
 * @param file - 画像ファイル
 * @returns Promise<{width: number; height: number}>
 */
export function getImageDimensions(
  file: File,
): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve({ width: img.width, height: img.height });
    img.onerror = () => reject(new Error("画像の読み込みに失敗しました"));

    const reader = new FileReader();
    reader.onload = (e) => {
      img.src = e.target?.result as string;
    };
    reader.onerror = () =>
      reject(new Error("ファイルの読み込みに失敗しました"));
    reader.readAsDataURL(file);
  });
}
