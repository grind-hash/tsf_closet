import type {
  AdventureNarrationVoice,
  AdventurePreset,
  AdventureSpeechStyle,
  AdventureStatus,
} from "../apis/adventure";

// Adventure（TSF シナリオ）画面で使う定数。セットアップ画面とプレイ画面で共有する。

// 新規作成で選べるミッション。恋愛シミュレーションを先頭に置く。
// "infiltration"(潜入)は「なりすまし・着替え」と体験が重複するため非表示
// (backend は保持しており、既存の潜入 run の表示・リプレイには影響しない)
export const PRESETS: AdventurePreset[] = [
  "romance",
  "escape",
  "negotiation",
  "disguise",
];

// 自動生成ミッションのターン数。backend/gateway/consts/adventure_turns.py と揃える
export const DEFAULT_MAX_TURNS = 15;

export const MIN_MAX_TURNS = 5;

export const MAX_MAX_TURNS = 30;

// 恋愛シミュレーションの日数。backend/gateway/consts/adventure_romance.py と揃える。
// 1日=昼夜2ターンなので scenario_max_turns には日数×2 を送る
export const ROMANCE_DEFAULT_DAYS = 7;

// 対面会話モードは日数でなくターン数(1ターン=1往復)。romance のクランプ(10〜60、偶数)に合わせる
export const COMPANION_DEFAULT_TURNS = 20;

export const COMPANION_TURN_OPTIONS = [10, 14, 20, 30, 40, 60] as const;

export const ROMANCE_MIN_DAYS = 5;

export const ROMANCE_MAX_DAYS = 30;

export const ROMANCE_DAY_OPTIONS = Array.from(
  { length: ROMANCE_MAX_DAYS - ROMANCE_MIN_DAYS + 1 },
  (_, index) => ROMANCE_MIN_DAYS + index,
);

// romance の主人公既定キャラクター。backend/gateway/consts/adventure_romance.py と揃える
export const ROMANCE_DEFAULT_PLAYER_ID = "char1";

// 主人公セレクトで「セッションの姿を使う」を表す特殊値
export const ROMANCE_PLAYER_SESSION_VALUE = "__session__";

export function clampMaxTurns(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_MAX_TURNS;
  return Math.min(MAX_MAX_TURNS, Math.max(MIN_MAX_TURNS, Math.round(value)));
}

// 主人公ドックは他のHUDパネルと排他にせず、開いたままプレイできるようにする
export const PROTAGONIST_DOCK_STORAGE_KEY = "adventure_protagonist_dock_open";

// backend/gateway/consts/adventure_narration.py と揃える
export const NARRATION_VOICES: AdventureNarrationVoice[] = [
  "second_person",
  "third_person",
  "first_person",
];

export const DEFAULT_NARRATION_PRONOUN = "僕";

export const NARRATION_PRONOUN_SUGGESTIONS = [
  "僕",
  "俺",
  "私",
  "わたし",
  "あたし",
];

export const NARRATION_PRONOUN_MAX_LENGTH = 10;

// backend/gateway/consts/adventure_speech.py と揃える
export const SPEECH_STYLES: AdventureSpeechStyle[] = [
  "polite",
  "casual",
  "formal",
  "custom",
];

export const DEFAULT_SPEECH_STYLE: AdventureSpeechStyle = "polite";

export const SPEECH_CUSTOM_MAX_LENGTH = 120;

export const PARTNER_SPEECH_STYLE_MAX_LENGTH = 200;

// backend/gateway/consts/adventure_romance.py の ROMANCE_PLAYER_NAME_MAX_LENGTH と揃える
export const ROMANCE_PLAYER_NAME_MAX_LENGTH = 40;

// 制約(1行1件)の上限件数。backend の consts/adventure_setup.py と合わせる
export const SCENARIO_CONSTRAINTS_MAX_ITEMS = 20;

export const SCENARIO_CONSTRAINTS_MAX_LENGTH = 2000;

// セットアップで選んだ語りと画像オプションは次回の作成時にも引き継ぐ。
// 精密参照はAnlasを追加消費するため保存対象に含めず、常に既定OFFから始める
export const SETUP_PREFS_STORAGE_KEY = "adventure_setup_prefs";

export type RunFilter = "all" | AdventureStatus;

export const RUN_FILTERS: RunFilter[] = [
  "all",
  "active",
  "success",
  "partial",
  "failure",
];

export const PORTRAIT_ALPHA_OPTIONS = { threshold: 12, featherRadius: 1.8 };

// 現実改変の宣言記法。判定はサーバ側 _detect_reality_declaration と揃える
export const REALITY_DECLARATION_PATTERN =
  /^\s*(?:\[\s*(?:現実改変|reality(?:[ _-]?alteration)?)\s*\]\s*[:：]?|(?:現実改変|reality(?:[ _-]?alteration)?)\s*[:：])\s*\S/i;
