import { describe, expect, it } from "vitest";
import type { AdventureRunSetup } from "../apis/adventure";
import {
  DEFAULT_NARRATION_PRONOUN,
  ROMANCE_MAX_DAYS,
  ROMANCE_PLAYER_CHARACTER_VALUE,
  ROMANCE_PLAYER_SESSION_VALUE,
} from "../constants/adventure";
import {
  formValuesFromRunSetup,
  romancePlayerSelectValue,
} from "./adventureRunSetup";

function makeSetup(
  overrides: Partial<AdventureRunSetup> = {},
): AdventureRunSetup {
  return {
    run_id: "run-1",
    title: "恋愛シミュレーション",
    preset: "romance",
    scenario_template_id: null,
    setting: "海辺の町",
    objective: "7日以内に想いを通わせる",
    constraints: ["門限は22時", "  ", "嘘はつかない"],
    max_turns: 14,
    total_days: 7,
    companion_mode: false,
    source_session_id: null,
    source_history_id: null,
    source_prompt_expander_entry_id: "pe-1",
    source_character_preset_id: null,
    narration_voice: "first_person",
    narration_pronoun: "俺",
    player_speech_style: "custom",
    player_speech_custom: "ぶっきらぼう",
    partner_speech_style: "敬語",
    romance_player_character_id: "char2",
    romance_player_session_id: null,
    romance_player_history_id: null,
    romance_player_prompt_expander_entry_id: null,
    romance_player_character_preset_id: null,
    romance_player_name: "エミ",
    ...overrides,
  };
}

describe("formValuesFromRunSetup", () => {
  it("恋愛シミュレーションの設定を作成フォームの値へ写す", () => {
    const values = formValuesFromRunSetup(makeSetup());

    expect(values.preset).toBe("romance");
    expect(values.scenarioSetting).toBe("海辺の町");
    expect(values.scenarioObjective).toBe("7日以内に想いを通わせる");
    expect(values.scenarioConstraints).toBe("門限は22時\n嘘はつかない");
    expect(values.romanceDays).toBe(7);
    // 恋愛はターン数の欄を使わないため、今のフォームの値を残す
    expect(values.scenarioMaxTurns).toBeNull();
    expect(values.companionTurns).toBeNull();
    expect(values.narrationVoice).toBe("first_person");
    expect(values.narrationPronoun).toBe("俺");
    expect(values.speechStyle).toBe("custom");
    expect(values.speechCustom).toBe("ぶっきらぼう");
    expect(values.partnerSpeechStyle).toBe("敬語");
    expect(values.source).toEqual({
      kind: "promptExpander",
      promptExpanderEntryId: "pe-1",
    });
    expect(values.player).toEqual({ kind: "template", characterId: "char2" });
    expect(values.romancePlayerName).toBe("エミ");
  });

  it("日数が無い旧 run はターン数から日数を逆算し、範囲へ丸める", () => {
    expect(
      formValuesFromRunSetup(makeSetup({ total_days: null, max_turns: 10 }))
        .romanceDays,
    ).toBe(5);
    expect(
      formValuesFromRunSetup(makeSetup({ total_days: 99 })).romanceDays,
    ).toBe(ROMANCE_MAX_DAYS);
  });

  it("対面会話モードの run はターン数を最も近い選択肢へ寄せ、日数は残す", () => {
    const values = formValuesFromRunSetup(
      makeSetup({ companion_mode: true, total_days: null, max_turns: 22 }),
    );
    expect(values.companionTurns).toBe(20);
    expect(values.romanceDays).toBeNull();
  });

  it("恋愛以外はターン数を写し、主人公・攻略対象の欄は写さない", () => {
    const values = formValuesFromRunSetup(
      makeSetup({
        preset: "escape",
        max_turns: 12,
        total_days: null,
        partner_speech_style: "残っていても使わない",
        romance_player_name: "",
      }),
    );
    expect(values.scenarioMaxTurns).toBe("12");
    expect(values.romanceDays).toBeNull();
    expect(values.player).toBeNull();
    expect(values.partnerSpeechStyle).toBe("");
    expect(values.romancePlayerName).toBe("");
  });

  it("開始素材はキャラクター、Prompt Expander、セッションの順に1つだけ選ぶ", () => {
    expect(
      formValuesFromRunSetup(
        makeSetup({
          source_character_preset_id: "preset-1",
          source_prompt_expander_entry_id: "pe-1",
        }),
      ).source,
    ).toEqual({ kind: "character", characterPresetId: "preset-1" });
    expect(
      formValuesFromRunSetup(
        makeSetup({
          source_prompt_expander_entry_id: null,
          source_session_id: "session-1",
          source_history_id: "history-1",
        }),
      ).source,
    ).toEqual({
      kind: "session",
      sessionId: "session-1",
      historyId: "history-1",
    });
    expect(
      formValuesFromRunSetup(
        makeSetup({ source_prompt_expander_entry_id: null }),
      ).source,
    ).toBeNull();
  });

  it("主人公はセッションの時点ごと取り直せる形で返す", () => {
    const values = formValuesFromRunSetup(
      makeSetup({
        romance_player_character_id: null,
        romance_player_session_id: "player-session",
        romance_player_history_id: "player-history",
      }),
    );
    expect(values.player).toEqual({
      kind: "session",
      sessionId: "player-session",
      historyId: "player-history",
    });
  });

  it("不正な語り・口調は既定値へ倒す", () => {
    const values = formValuesFromRunSetup(
      makeSetup({
        narration_voice: "unknown" as AdventureRunSetup["narration_voice"],
        narration_pronoun: "  ",
        player_speech_style: "x" as AdventureRunSetup["player_speech_style"],
      }),
    );
    expect(values.narrationVoice).toBe("second_person");
    expect(values.narrationPronoun).toBe(DEFAULT_NARRATION_PRONOUN);
    expect(values.speechStyle).toBe("polite");
  });
});

describe("romancePlayerSelectValue", () => {
  it("主人公の種類を主人公セレクトの値へ変換する", () => {
    expect(
      romancePlayerSelectValue({ kind: "template", characterId: "char2" }),
    ).toBe("char2");
    expect(
      romancePlayerSelectValue({
        kind: "character",
        characterPresetId: "preset-1",
      }),
    ).toBe(ROMANCE_PLAYER_CHARACTER_VALUE);
    expect(
      romancePlayerSelectValue({
        kind: "promptExpander",
        promptExpanderEntryId: "pe-1",
      }),
    ).toBe(ROMANCE_PLAYER_SESSION_VALUE);
    expect(
      romancePlayerSelectValue({
        kind: "session",
        sessionId: "s",
        historyId: null,
      }),
    ).toBe(ROMANCE_PLAYER_SESSION_VALUE);
  });
});
