import { beforeEach, describe, expect, it } from "vitest";
import {
  NARRATION_PRONOUN_MAX_LENGTH,
  NARRATION_VOICES,
  SETUP_PREFS_STORAGE_KEY,
  SPEECH_CUSTOM_MAX_LENGTH,
  SPEECH_STYLES,
} from "../constants/adventure";
import {
  normalizeNarrationPronoun,
  normalizeNarrationVoice,
  normalizeSpeechCustom,
  normalizeSpeechStyle,
  readSetupPrefs,
} from "./adventureSetupPrefs";

beforeEach(() => {
  localStorage.clear();
});

describe("readSetupPrefs", () => {
  it("未保存・壊れた JSON・オブジェクト以外は空を返す", () => {
    expect(readSetupPrefs()).toEqual({});
    localStorage.setItem(SETUP_PREFS_STORAGE_KEY, "{broken");
    expect(readSetupPrefs()).toEqual({});
    localStorage.setItem(SETUP_PREFS_STORAGE_KEY, JSON.stringify("text"));
    expect(readSetupPrefs()).toEqual({});
  });

  it("保存済みのオブジェクトをそのまま返す", () => {
    localStorage.setItem(
      SETUP_PREFS_STORAGE_KEY,
      JSON.stringify({ companionMode: true, imageModel: "default" }),
    );
    expect(readSetupPrefs()).toEqual({
      companionMode: true,
      imageModel: "default",
    });
  });
});

describe("normalize helpers", () => {
  it("語り手の声と口調は既知の値だけを通す", () => {
    expect(normalizeNarrationVoice(NARRATION_VOICES[0])).toBe(
      NARRATION_VOICES[0],
    );
    expect(normalizeNarrationVoice("unknown-voice")).toBeNull();
    expect(normalizeSpeechStyle(SPEECH_STYLES[0])).toBe(SPEECH_STYLES[0]);
    expect(normalizeSpeechStyle(42)).toBeNull();
  });

  it("一人称は前後の空白を除いて上限まで切り詰め、空は null", () => {
    expect(normalizeNarrationPronoun("  僕  ")).toBe("僕");
    expect(normalizeNarrationPronoun("   ")).toBeNull();
    expect(normalizeNarrationPronoun(null)).toBeNull();
    expect(
      normalizeNarrationPronoun("あ".repeat(NARRATION_PRONOUN_MAX_LENGTH + 5)),
    ).toHaveLength(NARRATION_PRONOUN_MAX_LENGTH);
  });

  it("自由入力の口調は上限まで切り詰め、文字列以外は null", () => {
    expect(normalizeSpeechCustom(" ですわ口調 ")).toBe("ですわ口調");
    expect(normalizeSpeechCustom(undefined)).toBeNull();
    expect(
      normalizeSpeechCustom("x".repeat(SPEECH_CUSTOM_MAX_LENGTH + 1)),
    ).toHaveLength(SPEECH_CUSTOM_MAX_LENGTH);
  });
});
