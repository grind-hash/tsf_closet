import type { PreciseReferenceFormat } from "../constants/novelaiImageModels";
import type { PreciseReference, PreciseReferenceType } from "../types";

/** 精密参照の強度の上限（送信形式ごと。V5 は 5.0 まで上げられる） */
export const PRECISE_REFERENCE_STRENGTH_MAX: Record<
  PreciseReferenceFormat,
  number
> = { v4_5: 1, v5: 5 };

/**
 * 精密参照を新しく追加したときの強度の初期値。V5 は公式が高めの強度を勧めているため
 * V4.5 より高くする
 */
export const DEFAULT_PRECISE_REFERENCE_STRENGTH: Record<
  PreciseReferenceFormat,
  number
> = { v4_5: 0.6, v5: 1 };

/** 精密参照1枚あたりの Anlas 消費（V4.5・V5 共通） */
export const ANLAS_PER_PRECISE_REFERENCE = 5;

/** 「衣装も参照する」が効く種別（キャラクター＆絵柄・キャラクター）か */
export function referenceTypeUsesOutfit(type: PreciseReferenceType): boolean {
  return type === "character" || type === "character&style";
}

/** その送信形式で送れる種別か（衣装参照は V5 のみ） */
export function isReferenceTypeSupported(
  type: PreciseReferenceType,
  format: PreciseReferenceFormat,
): boolean {
  return type !== "costume" || format === "v5";
}

/** 強度を送信形式の上限に収める */
export function clampReferenceStrength(
  strength: number,
  format: PreciseReferenceFormat,
): number {
  return Math.min(
    Math.max(strength, 0),
    PRECISE_REFERENCE_STRENGTH_MAX[format],
  );
}

/** play/stream へ送る精密参照1件分 */
export interface SendablePreciseReference {
  imageData: string;
  type: PreciseReferenceType;
  includeOutfit: boolean;
  strength: number;
  fidelity: number;
}

/**
 * 有効な参照があっても、この手番では1枚も送らない理由。
 * unsupportedModel: 精密参照に非対応のモデル（V5 節約モード）
 * inpaintV5: V5 のインペイント（NovelAI が精密参照つきインペイントに未対応）
 */
export type PreciseReferenceSkipReason = "unsupportedModel" | "inpaintV5";

/**
 * この手番で実際に送る精密参照を決める。Anlas の枚数計算と送信本文の両方で使う。
 * V4.5 では衣装参照を除き、強度を 1.0 に丸める。
 */
export function resolveSendablePreciseReferences(
  refs: readonly PreciseReference[],
  {
    format,
    maskActive,
  }: { format: PreciseReferenceFormat | null; maskActive: boolean },
): {
  references: SendablePreciseReference[];
  skipReason: PreciseReferenceSkipReason | null;
} {
  const enabled = refs.filter((ref) => ref.enabled);
  if (enabled.length === 0) return { references: [], skipReason: null };
  if (format === null) {
    return { references: [], skipReason: "unsupportedModel" };
  }
  if (format === "v5" && maskActive) {
    return { references: [], skipReason: "inpaintV5" };
  }
  const references = enabled
    .filter((ref) => isReferenceTypeSupported(ref.type, format))
    .map((ref) => ({
      imageData: ref.imageData,
      type: ref.type,
      includeOutfit: ref.includeOutfit,
      strength: clampReferenceStrength(ref.strength, format),
      fidelity: ref.fidelity,
    }));
  return { references, skipReason: null };
}
