import { cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePlayTurn } from "./usePlayTurn";

const mocks = vi.hoisted(() => ({
  game: { state: {} as Record<string, unknown> },
  settings: {
    state: {} as Record<string, unknown>,
    isNovelaiV5Active: false,
  },
  startPostStream: vi.fn(),
}));

vi.mock("../contexts/GameContext", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../contexts/GameContext")>()),
  useGame: () => mocks.game,
}));

vi.mock("../contexts/SettingsContext", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../contexts/SettingsContext")>()),
  useSettings: () => mocks.settings,
}));

vi.mock("./useGameSSE", () => ({
  useGameSSE: () => ({ startPostStream: mocks.startPostStream }),
}));

function setState({
  isTransforming = false,
  imageProvider = "novelai",
  isNovelaiV5Active = false,
}: {
  isTransforming?: boolean;
  imageProvider?: string;
  isNovelaiV5Active?: boolean;
} = {}) {
  mocks.game = { state: { sessionId: "session-1", isTransforming } };
  mocks.settings = {
    state: {
      language: "ja",
      historyLookbackTargets: { dress_up: true },
      playMemoryEnabled: true,
      seed: 42,
      enableSurroundingsImage: true,
      surroundingsIncludePeople: false,
      clothingColorConsistency: true,
      respectClothingLayers: false,
      enableMultiplePeople: false,
      multiCharacterPanelEnabled: true,
      imageProvider,
    },
    isNovelaiV5Active,
  };
}

beforeEach(() => {
  mocks.startPostStream.mockReset();
  setState();
});

afterEach(() => {
  cleanup();
});

describe("usePlayTurn", () => {
  it("builds the same play/stream body as the normal play screen", () => {
    const { result } = renderHook(() => usePlayTurn());

    result.current(
      "優しい青色のドレス",
      undefined,
      "costume",
      {
        inpaintStrength: 0.6,
        inpaintNoise: 0.1,
        negativePrompt: "lowres",
        characterReferences: [
          {
            imageData: "data:image/png;base64,AAAA",
            type: "character",
            strength: 1,
            fidelity: 0.8,
          },
        ],
      },
      "dress_up",
      "token-1",
      false,
    );

    expect(mocks.startPostStream).toHaveBeenCalledTimes(1);
    const [url, body, token] = mocks.startPostStream.mock.calls[0];
    expect(url).toMatch(/\/game\/play\/stream$/);
    expect(token).toBe("token-1");
    expect(body).toEqual({
      session_id: "session-1",
      instruction: "優しい青色のドレス",
      transformation_type: "costume",
      language: "ja",
      instruction_type: "dress_up",
      use_history_lookback: true,
      use_memory: false,
      use_play_memory: true,
      seed: 42,
      enable_surroundings_image: true,
      clothing_color_consistency: true,
      use_character_panel: true,
      inpaint_strength: 0.6,
      inpaint_noise: 0.1,
      negative_prompt: "lowres",
      character_references: [
        { image: "AAAA", type: "character", strength: 1, fidelity: 0.8 },
      ],
    });
  });

  it("drops precise references on V5 models and fills NovelAI defaults", () => {
    setState({ isNovelaiV5Active: true });
    const { result } = renderHook(() => usePlayTurn());

    result.current("指示", undefined, "costume", {
      characterReferences: [
        { imageData: "AAAA", type: "character", strength: 1, fidelity: 1 },
      ],
    });

    const body = mocks.startPostStream.mock.calls[0][1];
    expect(body.character_references).toBeUndefined();
    expect(typeof body.inpaint_strength).toBe("number");
    expect(typeof body.inpaint_noise).toBe("number");
  });

  it("sends the NSFW override only when a turn asks for it", () => {
    const { result } = renderHook(() => usePlayTurn());

    result.current("指示", undefined, "costume", { nsfwMode: false });
    result.current("指示", undefined, "costume", { nsfwMode: true });
    result.current("指示");

    const bodies = mocks.startPostStream.mock.calls.map((call) => call[1]);
    expect(bodies[0].nsfw_mode).toBe(false);
    expect(bodies[1].nsfw_mode).toBe(true);
    expect("nsfw_mode" in bodies[2]).toBe(false);
  });

  it("does not send while a turn is already running", () => {
    setState({ isTransforming: true });
    const { result } = renderHook(() => usePlayTurn());

    result.current("指示");

    expect(mocks.startPostStream).not.toHaveBeenCalled();
  });
});
