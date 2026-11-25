import type { AdventurePreset } from "../apis/adventure";
import { ANLAS_PER_PRECISE_REFERENCE } from "./preciseReferences";

/** NovelAI character reference 1指定あたりの追加Anlas消費量（V4.5・V5 共通） */
export const ANLAS_COST_PER_REFERENCE = ANLAS_PER_PRECISE_REFERENCE;

export interface AdventureAnlasEstimate {
  min: number;
  max: number;
}

/**
 * 精密参照ON時の追加Anlas消費量を見積もる。
 *
 * 追加消費は character reference の指定数に比例し、背景生成は参照を使わない。
 * 単価と参照数はモデル(V4.5 / V5 Full / V5 Curated)に依らない。Adventure は
 * インペイントを使わないため、V5 で参照が落ちる手番もない。
 * 参照数の内訳 (backend/gateway/services/adventure_service.py):
 * - 主人公立ち絵: 1
 * - 攻略対象立ち絵 (romanceのみ。ターン中は非合成時のみ、開始時は常に生成): 1
 * - 合成シーン (合成ON時): 1 + romanceで攻略対象が場面に登場するターンのみ+1
 */
export function estimateAdventureAnlas(params: {
  kind: "turn" | "start";
  preset: AdventurePreset;
  enableCompositeScene: boolean;
}): AdventureAnlasEstimate {
  const { kind, preset, enableCompositeScene } = params;
  const isRomance = preset === "romance";
  let minRefs: number;
  let maxRefs: number;
  if (enableCompositeScene) {
    minRefs = 2;
    maxRefs = isRomance ? 3 : 2;
    if (kind === "start" && isRomance) {
      minRefs += 1;
      maxRefs += 1;
    }
  } else {
    minRefs = isRomance ? 2 : 1;
    maxRefs = minRefs;
  }
  return {
    min: minRefs * ANLAS_COST_PER_REFERENCE,
    max: maxRefs * ANLAS_COST_PER_REFERENCE,
  };
}
