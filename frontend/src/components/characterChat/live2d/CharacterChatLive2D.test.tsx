import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "../../../i18n";
import CharacterChatLive2D, { LIVE2D_CAMERA_KEY } from "./CharacterChatLive2D";

// モデルの URL が無いスレッドにして、WebGL の読み込みを始めさせない
vi.mock("../../../contexts/CharacterChatContext", () => {
  const value = {
    activeThread: null,
    sending: false,
    pendingInput: null,
    error: null,
    voice: {
      currentKey: null,
      status: "idle",
      canSpeak: false,
      volume: 0,
      getLevel: () => 0,
    },
    setAvatarFailed: () => {},
  };
  return { useCharacterChat: () => value };
});

vi.mock("../../../contexts/NotificationContext", () => {
  const value = { showNotification: () => {} };
  return { useNotification: () => value };
});

vi.mock("./cubismPilotRenderer", () => ({
  CubismPilotRenderer: { create: vi.fn(() => new Promise(() => {})) },
}));

function pressed(name: string): string | null {
  return screen.getByRole("button", { name }).getAttribute("aria-pressed");
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("CharacterChatLive2D camera", () => {
  it("defaults to the full-body view", () => {
    render(<CharacterChatLive2D />);
    expect(pressed("全身")).toBe("true");
    expect(pressed("寄り")).toBe("false");
  });

  it("remembers the chosen view across remounts", () => {
    const first = render(<CharacterChatLive2D />);
    fireEvent.click(screen.getByRole("button", { name: "寄り" }));
    expect(localStorage.getItem(LIVE2D_CAMERA_KEY)).toBe("portrait");
    first.unmount();

    const second = render(<CharacterChatLive2D />);
    expect(pressed("寄り")).toBe("true");
    expect(
      second.container
        .querySelector(".character-chat-room__live2d")
        ?.getAttribute("data-camera"),
    ).toBe("portrait");
  });

  it("falls back to the full-body view for an unknown stored value", () => {
    localStorage.setItem(LIVE2D_CAMERA_KEY, "sideways");
    render(<CharacterChatLive2D />);
    expect(pressed("全身")).toBe("true");
  });
});
