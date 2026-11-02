import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchAdventureBgmCatalog } from "../apis/adventure";
import { SALON_SE_PREFS_STORAGE_KEY } from "../utils/bgmPreferences";
import { useSalonSoundEffects } from "./useSalonSoundEffects";

vi.mock("../apis/adventure", () => ({
  fetchAdventureBgmCatalog: vi.fn(),
}));

const fetchCatalog = vi.mocked(fetchAdventureBgmCatalog);

class FakeAudio {
  static created: FakeAudio[] = [];
  src: string;
  volume = 1;
  currentTime = 0;
  preload = "";
  play = vi.fn(() => Promise.resolve());

  constructor(src: string) {
    this.src = src;
    FakeAudio.created.push(this);
  }
}

beforeEach(() => {
  localStorage.clear();
  FakeAudio.created = [];
  vi.stubGlobal("Audio", FakeAudio);
  fetchCatalog.mockResolvedValue({
    default_key: "daily",
    tracks: [
      {
        key: "daily",
        url: "/api/adventure/bgm/audio/daily.ogg",
        file: "daily.ogg",
        description: "",
      },
      {
        key: "salon_se_register",
        url: "/api/adventure/bgm/audio/se01_salon_register.ogg",
        file: "se01_salon_register.ogg",
        description: "",
        scope: "salon_se",
      },
    ],
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  fetchCatalog.mockReset();
});

describe("useSalonSoundEffects", () => {
  it("サロン経営が OFF の間はカタログを取りに行かない", () => {
    const { result } = renderHook(() => useSalonSoundEffects(false));
    expect(fetchCatalog).not.toHaveBeenCalled();
    expect(result.current.available).toBe(false);
  });

  it("初回はミュートで、置かれている音があっても鳴らさない", async () => {
    const { result } = renderHook(() => useSalonSoundEffects(true));
    await waitFor(() => expect(result.current.available).toBe(true));
    expect(result.current.muted).toBe(true);
    expect(result.current.volume).toBe(0.5);

    act(() => result.current.play("register"));
    expect(FakeAudio.created).toHaveLength(0);
  });

  it("ON にすると1回鳴らして設定を保存し、その後は置かれている音だけを鳴らす", async () => {
    const { result } = renderHook(() => useSalonSoundEffects(true));
    await waitFor(() => expect(result.current.available).toBe(true));

    act(() => result.current.setMuted(false));
    expect(FakeAudio.created).toHaveLength(1);
    expect(FakeAudio.created[0].src).toContain("se01_salon_register.ogg");
    expect(FakeAudio.created[0].volume).toBe(0.5);
    expect(
      JSON.parse(localStorage.getItem(SALON_SE_PREFS_STORAGE_KEY) ?? "{}"),
    ).toEqual({ muted: false, volume: 0.5 });

    act(() => result.current.setVolume(0.8));
    act(() => result.current.play("register"));
    expect(FakeAudio.created).toHaveLength(1);
    expect(FakeAudio.created[0].play).toHaveBeenCalledTimes(2);
    expect(FakeAudio.created[0].volume).toBe(0.8);

    // ファイルが置かれていない音は鳴らさない
    act(() => result.current.play("doorbell"));
    expect(FakeAudio.created).toHaveLength(1);
  });

  it("効果音が1つも置かれていなければ available は false のまま", async () => {
    fetchCatalog.mockResolvedValue({ default_key: "daily", tracks: [] });
    const { result } = renderHook(() => useSalonSoundEffects(true));
    await waitFor(() => expect(fetchCatalog).toHaveBeenCalled());
    expect(result.current.available).toBe(false);
  });
});
