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

export interface AdventureTurnImageSettings {
  preset: AdventurePreset;
  enableCompositeScene: boolean;
  drawPortraitEveryTurn: boolean;
  drawPartnerEveryTurn: boolean;
  /**
   * 1on1 立ち絵モード(romance のみ)。ON のとき主人公立ち絵と合成シーンは
   * 設定に関わらず生成されず、攻略対象の立ち絵だけが描かれる
   */
  oneOnOneMode?: boolean;
}

/**
 * 1ターンの生成時間を実際のパイプライン挙動から見積もる(秒、5秒単位へ丸め)。
 *
 * 3つの設定は独立で、主人公立ち絵→攻略対象立ち絵(romance)→合成シーンの順に
 * 直列生成される。立ち絵の毎ターン生成OFFは合成・精密参照の有無に関わらず効き、
 * 省略した側は前ターンの1枚を使い回す(backend の visual_producer と同条件)。
 *
 * - 場面変化が無いターンは画像自体が省かれるため、これは上振れ側の目安
 * - romance の背景再生成(現在地・時間帯の変化時のみ)は含めない
 */
export function estimateAdventureTurnSeconds(
  params: AdventureTurnImageSettings,
): number {
  const {
    preset,
    enableCompositeScene,
    drawPortraitEveryTurn,
    drawPartnerEveryTurn,
    oneOnOneMode = false,
  } = params;
  const oneOnOne = preset === "romance" && oneOnOneMode;
  let seconds = TURN_BASE_SECONDS;
  if (drawPortraitEveryTurn && !oneOnOne) {
    seconds += ADVENTURE_PROGRESS_BUDGET_MS.portrait / 1000;
  }
  if (preset === "romance" && drawPartnerEveryTurn) {
    seconds += ADVENTURE_PROGRESS_BUDGET_MS.partner / 1000;
  }
  if (enableCompositeScene && !oneOnOne) {
    seconds += ADVENTURE_PROGRESS_BUDGET_MS.composite / 1000;
  }
  return Math.round(seconds / 5) * 5;
}

/**
 * そのターンに画像生成が一切走らない設定かどうか。
 * backend の visual_producer が画像工程ごとスキップする条件と揃える。
 * romance の背景更新(現在地・時間帯の変化時)はこの判定の対象外。
 */
export function isAdventureTurnTextOnly(
  params: AdventureTurnImageSettings,
): boolean {
  const {
    preset,
    enableCompositeScene,
    drawPortraitEveryTurn,
    drawPartnerEveryTurn,
    oneOnOneMode = false,
  } = params;
  if (preset === "romance" && oneOnOneMode) {
    return !drawPartnerEveryTurn;
  }
  if (enableCompositeScene || drawPortraitEveryTurn) return false;
  return !(preset === "romance" && drawPartnerEveryTurn);
}
