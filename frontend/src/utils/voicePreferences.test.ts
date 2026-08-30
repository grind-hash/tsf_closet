import { afterEach, describe, expect, it } from "vitest";
import {
  clampVoiceSpeed,
  DEFAULT_VOICE_PREFERENCES,
  loadVoicePreferences,
  MAX_VOICE_SPEED,
  MIN_VOICE_SPEED,
  saveVoicePreferences,
  VOICE_PREFS_STORAGE_KEY,
} from "./voicePreferences";

describe("voicePreferences", () => {
  afterEach(() => {
    localStorage.removeItem(VOICE_PREFS_STORAGE_KEY);
  });

  it("defaults to off at 50% volume and normal speed", () => {
    expect(DEFAULT_VOICE_PREFERENCES).toEqual({
      enabled: false,
      volume: 0.5,
      speed: 1,
    });
    expect(loadVoicePreferences()).toEqual({
      enabled: false,
      volume: 0.5,
      speed: 1,
    });
  });

  it("keeps a saved volume and falls back to 50% when the value is invalid", () => {
    saveVoicePreferences({ enabled: true, volume: 0.25, speed: 1 });
    expect(loadVoicePreferences()).toEqual({
      enabled: true,
      volume: 0.25,
      speed: 1,
    });
    localStorage.setItem(
      VOICE_PREFS_STORAGE_KEY,
      JSON.stringify({ enabled: true, volume: "loud" }),
    );
    expect(loadVoicePreferences().volume).toBe(0.5);
  });

  it("keeps a saved speed and falls back to 1x when the value is missing or invalid", () => {
    saveVoicePreferences({ enabled: true, volume: 0.5, speed: 1.4 });
    expect(loadVoicePreferences().speed).toBe(1.4);

    // speed を持たない旧形式の設定でも既定値で読める
    localStorage.setItem(
      VOICE_PREFS_STORAGE_KEY,
      JSON.stringify({ enabled: true, volume: 0.5 }),
    );
    expect(loadVoicePreferences().speed).toBe(1);

    localStorage.setItem(
      VOICE_PREFS_STORAGE_KEY,
      JSON.stringify({ enabled: true, volume: 0.5, speed: "fast" }),
    );
    expect(loadVoicePreferences().speed).toBe(1);
  });

  it("clamps the speed to the supported range", () => {
    expect(clampVoiceSpeed(0.1)).toBe(MIN_VOICE_SPEED);
    expect(clampVoiceSpeed(9)).toBe(MAX_VOICE_SPEED);
    expect(clampVoiceSpeed(Number.NaN)).toBe(1);
    expect(clampVoiceSpeed(1.25)).toBe(1.25);

    saveVoicePreferences({ enabled: true, volume: 0.5, speed: 9 });
    expect(loadVoicePreferences().speed).toBe(MAX_VOICE_SPEED);
  });
});
