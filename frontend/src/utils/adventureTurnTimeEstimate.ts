import type { AdventurePreset } from "../apis/adventure";

/**
 * 各生成工程の見なし所要時間(ms)。実測に合わせて調整する。
 * AdventureScreen の進捗バーと1ターンの時間見積もりの唯一の情報源。
 */
export const ADVENTURE_PROGRESS_BUDGET_MS = {
  clue_check: 12_000,
  portrait: 18_000,
  partner: 18_000,
  composite: 20_000,
  image_single: 20_000,
} as const;

/**
 * 物語ストリーム + 並列の判定/ビジュアルLLM のベース時間(秒)。
 * 実測では画像なしでも1ターン最短20秒程度かかる。
 * 判定LLMはビジュアルLLMと並列実行のため、手掛かり抽出のON/OFFは
 * この見積もりを変えない。
 */
export const TURN_BASE_SECONDS = 20;

/**
 * 1ターンの生成時間を実際のパイプライン挙動から見積もる(秒、5秒単位へ丸め)。
 *
 * - 合成ON: 主人公立ち絵→合成シーンを直列生成する(スキップ不可)。
 *   攻略対象の立ち絵は合成シーンに含まれるため単独生成されない
 * - 合成OFF: 主人公/攻略対象(romance)の立ち絵を設定に応じて生成する。
 *   精密参照ONはスキップ不可(backend の allow_portrait_skip と同条件)
 * - 場面変化が無いターンは画像自体が省かれるため、これは上振れ側の目安
 * - romance の背景再生成(現在地・時間帯の変化時のみ)は含めない
 */
export function estimateAdventureTurnSeconds(params: {
  preset: AdventurePreset;
  usePreciseReference: boolean;
  enableCompositeScene: boolean;
  drawPortraitEveryTurn: boolean;
  drawPartnerEveryTurn: boolean;
}): number {
  const {
    preset,
    usePreciseReference,
    enableCompositeScene,
    drawPortraitEveryTurn,
    drawPartnerEveryTurn,
  } = params;
  const forcePortrait = usePreciseReference || enableCompositeScene;
  let seconds = TURN_BASE_SECONDS;
  if (enableCompositeScene) {
    seconds += ADVENTURE_PROGRESS_BUDGET_MS.portrait / 1000;
    seconds += ADVENTURE_PROGRESS_BUDGET_MS.composite / 1000;
  } else {
    if (drawPortraitEveryTurn || forcePortrait) {
      seconds += ADVENTURE_PROGRESS_BUDGET_MS.portrait / 1000;
    }
    if (preset === "romance" && (drawPartnerEveryTurn || forcePortrait)) {
      seconds += ADVENTURE_PROGRESS_BUDGET_MS.partner / 1000;
    }
  }
  return Math.round(seconds / 5) * 5;
}
