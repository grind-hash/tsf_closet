import { afterEach, describe, expect, it } from "vitest";
import {
  loadSpeechInputPreferences,
  SPEECH_INPUT_PREFS_STORAGE_KEY,
  saveSpeechInputPreferences,
} from "./speechInputPreferences";

afterEach(() => {
  localStorage.removeItem(SPEECH_INPUT_PREFS_STORAGE_KEY);
});

describe("speechInputPreferences", () => {
  it("defaults to autoSend off", () => {
    expect(loadSpeechInputPreferences()).toEqual({ autoSend: false });
  });

  it("round-trips the saved value", () => {
    saveSpeechInputPreferences({ autoSend: true });
    expect(loadSpeechInputPreferences()).toEqual({ autoSend: true });
  });

  it("falls back to defaults for corrupted storage", () => {
    localStorage.setItem(SPEECH_INPUT_PREFS_STORAGE_KEY, "not-json");
    expect(loadSpeechInputPreferences()).toEqual({ autoSend: false });
    localStorage.setItem(
      SPEECH_INPUT_PREFS_STORAGE_KEY,
      JSON.stringify({ autoSend: "yes" }),
    );
    expect(loadSpeechInputPreferences()).toEqual({ autoSend: false });
  });
});
