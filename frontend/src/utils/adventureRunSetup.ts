import type {
  AdventureNarrationVoice,
  AdventurePreset,
  AdventureRunSetup,
  AdventureSpeechStyle,
} from "../apis/adventure";
import {
  COMPANION_DEFAULT_TURNS,
  COMPANION_TURN_OPTIONS,
  clampMaxTurns,
  DEFAULT_NARRATION_PRONOUN,
  DEFAULT_SPEECH_STYLE,
  PARTNER_SPEECH_STYLE_MAX_LENGTH,
  ROMANCE_DEFAULT_DAYS,
  ROMANCE_MAX_DAYS,
  ROMANCE_MIN_DAYS,
  ROMANCE_PLAYER_CHARACTER_VALUE,
  ROMANCE_PLAYER_NAME_MAX_LENGTH,
  ROMANCE_PLAYER_SESSION_VALUE,
  SCENARIO_CONSTRAINTS_MAX_LENGTH,
} from "../constants/adventure";
import {
  normalizeNarrationPronoun,
  normalizeNarrationVoice,
  normalizeSpeechCustom,
  normalizeSpeechStyle,
} from "./adventureSetupPrefs";

// 舞台・ゴールの入力欄の上限(AdventureHub の maxLength と揃える)
const SCENARIO_TEXT_MAX_LENGTH = 600;

/** セッションを取り直す対象。historyId が null なら現在の状態 */
export type AdventureRunSetupSessionTarget = {
  kind: "session";
  sessionId: string;
  historyId: string | null;
};

/** 開始素材として取り直す対象。種類ごとに1つだけ入る */
export type AdventureRunSetupSource =
  | { kind: "character"; characterPresetId: string }
  | { kind: "promptExpander"; promptExpanderEntryId: string }
  | AdventureRunSetupSessionTarget
  | null;

/** 恋愛シミュレーションの主人公として取り直す対象 */
export type AdventureRunSetupPlayer =
  | { kind: "template"; characterId: string }
  | { kind: "character"; characterPresetId: string }
  | { kind: "promptExpander"; promptExpanderEntryId: string }
  | AdventureRunSetupSessionTarget
  | null;

/** 作成フォームへそのまま入れられる値 */
export interface AdventureRunSetupFormValues {
  preset: AdventurePreset;
  scenarioSetting: string;
  scenarioObjective: string;
  scenarioConstraints: string;
  /** 元の run が使っていた長さの欄だけ値が入り、他は null(今のフォームの値を残す) */
  scenarioMaxTurns: string | null;
  romanceDays: number | null;
  companionTurns: number | null;
  narrationVoice: AdventureNarrationVoice;
  narrationPronoun: string;
  speechStyle: AdventureSpeechStyle;
  speechCustom: string;
  partnerSpeechStyle: string;
  source: AdventureRunSetupSource;
  /** 恋愛シミュレーション以外、または主人公情報の無い旧 run は null */
  player: AdventureRunSetupPlayer;
  romancePlayerName: string;
}

function clampRomanceDays(days: number): number {
  if (!Number.isFinite(days)) return ROMANCE_DEFAULT_DAYS;
  return Math.min(
    ROMANCE_MAX_DAYS,
    Math.max(ROMANCE_MIN_DAYS, Math.round(days)),
  );
}

// 選択肢に無いターン数は最も近い選択肢へ寄せる(セレクトに値が無いと空欄になるため)
function nearestCompanionTurns(turns: number): number {
  if (!Number.isFinite(turns)) return COMPANION_DEFAULT_TURNS;
  return COMPANION_TURN_OPTIONS.reduce<number>(
    (best, option) =>
      Math.abs(option - turns) < Math.abs(best - turns) ? option : best,
    COMPANION_TURN_OPTIONS[0],
  );
}

function setupSource(setup: AdventureRunSetup): AdventureRunSetupSource {
  if (setup.source_character_preset_id) {
    return {
      kind: "character",
      characterPresetId: setup.source_character_preset_id,
    };
  }
  if (setup.source_prompt_expander_entry_id) {
    return {
      kind: "promptExpander",
      promptExpanderEntryId: setup.source_prompt_expander_entry_id,
    };
  }
  if (setup.source_session_id) {
    return {
      kind: "session",
      sessionId: setup.source_session_id,
      historyId: setup.source_history_id,
    };
  }
  return null;
}

function setupPlayer(setup: AdventureRunSetup): AdventureRunSetupPlayer {
  if (setup.preset !== "romance") return null;
  if (setup.romance_player_character_preset_id) {
    return {
      kind: "character",
      characterPresetId: setup.romance_player_character_preset_id,
    };
  }
  if (setup.romance_player_prompt_expander_entry_id) {
    return {
      kind: "promptExpander",
      promptExpanderEntryId: setup.romance_player_prompt_expander_entry_id,
    };
  }
  if (setup.romance_player_session_id) {
    return {
      kind: "session",
      sessionId: setup.romance_player_session_id,
      historyId: setup.romance_player_history_id,
    };
  }
  if (setup.romance_player_character_id) {
    return { kind: "template", characterId: setup.romance_player_character_id };
  }
  return null;
}

/** 主人公の取り直し対象から、主人公セレクトに入れる値を決める */
export function romancePlayerSelectValue(
  player: Exclude<AdventureRunSetupPlayer, null>,
): string {
  if (player.kind === "template") return player.characterId;
  if (player.kind === "character") return ROMANCE_PLAYER_CHARACTER_VALUE;
  return ROMANCE_PLAYER_SESSION_VALUE;
}

/**
 * 遊んだ run の設定を、作成フォームの値へ変換する。
 * 開始素材と主人公は ID だけを返し、表示用の選択オブジェクトは呼び出し側で取り直す。
 */
export function formValuesFromRunSetup(
  setup: AdventureRunSetup,
): AdventureRunSetupFormValues {
  const romance = setup.preset === "romance";
  const companion = romance && setup.companion_mode;
  return {
    preset: setup.preset,
    scenarioSetting: setup.setting.slice(0, SCENARIO_TEXT_MAX_LENGTH),
    scenarioObjective: setup.objective.slice(0, SCENARIO_TEXT_MAX_LENGTH),
    scenarioConstraints: setup.constraints
      .map((item) => item.trim())
      .filter(Boolean)
      .join("\n")
      .slice(0, SCENARIO_CONSTRAINTS_MAX_LENGTH),
    scenarioMaxTurns: romance ? null : String(clampMaxTurns(setup.max_turns)),
    // 恋愛は1日=昼夜2ターン。日数が返らない旧 run はターン数から逆算する
    romanceDays:
      romance && !companion
        ? clampRomanceDays(setup.total_days ?? Math.floor(setup.max_turns / 2))
        : null,
    companionTurns: companion ? nearestCompanionTurns(setup.max_turns) : null,
    narrationVoice:
      normalizeNarrationVoice(setup.narration_voice) ?? "second_person",
    narrationPronoun:
      normalizeNarrationPronoun(setup.narration_pronoun) ??
      DEFAULT_NARRATION_PRONOUN,
    speechStyle:
      normalizeSpeechStyle(setup.player_speech_style) ?? DEFAULT_SPEECH_STYLE,
    speechCustom: normalizeSpeechCustom(setup.player_speech_custom) ?? "",
    partnerSpeechStyle: romance
      ? setup.partner_speech_style
          .trim()
          .slice(0, PARTNER_SPEECH_STYLE_MAX_LENGTH)
      : "",
    source: setupSource(setup),
    player: setupPlayer(setup),
    romancePlayerName: romance
      ? setup.romance_player_name
          .trim()
          .slice(0, ROMANCE_PLAYER_NAME_MAX_LENGTH)
      : "",
  };
}
