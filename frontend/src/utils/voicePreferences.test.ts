import { afterEach, describe, expect, it } from "vitest";
import {
  DEFAULT_VOICE_PREFERENCES,
  loadVoicePreferences,
  saveVoicePreferences,
  VOICE_PREFS_STORAGE_KEY,
} from "./voicePreferences";

describe("voicePreferences", () => {
  afterEach(() => {
    localStorage.removeItem(VOICE_PREFS_STORAGE_KEY);
  });

  it("defaults to off at 50% volume", () => {
    expect(DEFAULT_VOICE_PREFERENCES).toEqual({ enabled: false, volume: 0.5 });
    expect(loadVoicePreferences()).toEqual({ enabled: false, volume: 0.5 });
  });

  it("keeps a saved volume and falls back to 50% when the value is invalid", () => {
    saveVoicePreferences({ enabled: true, volume: 0.25 });
    expect(loadVoicePreferences()).toEqual({ enabled: true, volume: 0.25 });
    localStorage.setItem(
      VOICE_PREFS_STORAGE_KEY,
      JSON.stringify({ enabled: true, volume: "loud" }),
    );
    expect(loadVoicePreferences()).toEqual({ enabled: true, volume: 0.5 });
  });
});
