import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  BGM_FADE_OUT_MS,
  BGM_PREFS_STORAGE_KEY,
  SALON_BGM_PREFS_STORAGE_KEY,
  useAdventureBgm,
} from "./useAdventureBgm";

vi.mock("../apis/adventure", () => ({
  fetchAdventureBgmCatalog: vi.fn(async () => ({
    default_key: "daily",
    tracks: [
      {
        key: "daily",
        url: "/bgm/daily.ogg",
        file: "daily.ogg",
        description: "",
      },
      {
        key: "salon_office",
        url: "/bgm/office.ogg",
        file: "office.ogg",
        description: "",
        scope: "salon",
      },
    ],
  })),
}));

const sources: string[] = [];
const instances: FakeAudio[] = [];

class FakeAudio {
  loop = false;
  preload = "";
  muted = false;
  volume = 1;
  paused = true;
  private currentSrc = "";
  constructor() {
    instances.push(this);
  }
  get src() {
    return this.currentSrc;
  }
  set src(value: string) {
    this.currentSrc = value;
    sources.push(value);
  }
  play() {
    this.paused = false;
    return Promise.resolve();
  }
  pause() {
    this.paused = true;
  }
  removeAttribute() {
    this.currentSrc = "";
  }
  load() {}
  addEventListener() {}
}

beforeEach(() => {
  sources.length = 0;
  instances.length = 0;
  vi.stubGlobal("Audio", FakeAudio);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  localStorage.removeItem(BGM_PREFS_STORAGE_KEY);
  localStorage.removeItem(SALON_BGM_PREFS_STORAGE_KEY);
});

describe("useAdventureBgm", () => {
  it("plays the requested salon track when it is in the catalog", async () => {
    const { result } = renderHook(() =>
      useAdventureBgm("salon_office", { fallbackToDefault: false }),
    );

    await waitFor(() => expect(result.current.playable).toBe(true));
    await waitFor(() => expect(sources).toEqual(["/bgm/office.ogg"]));
  });

  it("stays silent for a missing salon track instead of the scenario's default", async () => {
    const { result } = renderHook(() =>
      useAdventureBgm("salon_reveal", { fallbackToDefault: false }),
    );

    await waitFor(() => expect(result.current.playable).toBe(false));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(sources).toEqual([]);
  });

  it("keeps the salon's mute separate from the scenario's", async () => {
    // TSF シナリオで BGM を鳴らしていても、サロンは初めて開いたときミュートから始める
    localStorage.setItem(
      BGM_PREFS_STORAGE_KEY,
      JSON.stringify({ muted: false, volume: 0.8 }),
    );
    const { result, unmount } = renderHook(() =>
      useAdventureBgm("salon_office", {
        fallbackToDefault: false,
        prefsScope: "salon",
      }),
    );

    await waitFor(() => expect(result.current.playable).toBe(true));
    expect(result.current.muted).toBe(true);
    expect(result.current.volume).toBe(0.5);
    act(() => result.current.setMuted(false));

    // サロンで鳴らしても、TSF シナリオの設定は変わらない
    expect(
      JSON.parse(localStorage.getItem(SALON_BGM_PREFS_STORAGE_KEY) ?? "{}"),
    ).toEqual({
      muted: false,
      volume: 0.5,
    });
    expect(
      JSON.parse(localStorage.getItem(BGM_PREFS_STORAGE_KEY) ?? "{}"),
    ).toEqual({
      muted: false,
      volume: 0.8,
    });
    unmount();
  });

  it("keeps falling back to the default track for the scenario", async () => {
    const { result } = renderHook(() => useAdventureBgm("unknown_scene"));

    await waitFor(() => expect(result.current.playable).toBe(true));
    await waitFor(() => expect(sources).toEqual(["/bgm/daily.ogg"]));
  });

  it("fades the music out instead of cutting it when the screen is left", async () => {
    localStorage.setItem(
      BGM_PREFS_STORAGE_KEY,
      JSON.stringify({ muted: false, volume: 0.5 }),
    );
    const { unmount } = renderHook(() =>
      useAdventureBgm("salon_office", { fallbackToDefault: false }),
    );
    await waitFor(() => expect(instances[0]?.paused).toBe(false));
    await waitFor(() => expect(instances[0].volume).toBeGreaterThan(0));
    const audio = instances[0];
    const before = audio.volume;

    vi.useFakeTimers({
      toFake: ["setInterval", "clearInterval", "performance"],
    });
    unmount();
    vi.advanceTimersByTime(BGM_FADE_OUT_MS / 2);

    // 途中では鳴ったまま音量だけが下がっている
    expect(audio.paused).toBe(false);
    expect(audio.volume).toBeLessThan(before);
    expect(audio.volume).toBeGreaterThan(0);

    vi.advanceTimersByTime(BGM_FADE_OUT_MS);
    expect(audio.paused).toBe(true);
    expect(audio.src).toBe("");
  });
});
