import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AvatarExpressionKey } from "../../constants/companionAvatar";
import "../../i18n";
import CharacterChatExpressionMenu, {
  type CharacterChatStageKind,
} from "./CharacterChatExpressionMenu";

const mocks = vi.hoisted(() => ({
  expressionPreview: null as AvatarExpressionKey | null,
  setExpressionPreview: vi.fn(),
  expressionProgress: null as {
    expression: string;
    done: number;
    total: number;
  } | null,
}));

vi.mock("../../contexts/CharacterChatContext", async (importOriginal) => ({
  ...(await importOriginal<
    typeof import("../../contexts/CharacterChatContext")
  >()),
  useCharacterChat: () => ({
    expressionPreview: mocks.expressionPreview,
    setExpressionPreview: mocks.setExpressionPreview,
    expressionProgress: mocks.expressionProgress,
  }),
}));

beforeEach(() => {
  localStorage.clear();
  mocks.expressionPreview = null;
  mocks.setExpressionPreview.mockReset();
  mocks.expressionProgress = null;
});

afterEach(() => {
  cleanup();
});

const button = (name: string) =>
  screen.getByRole<HTMLButtonElement>("button", { name });

function renderMenu(
  stageKind: CharacterChatStageKind,
  options: {
    missing?: string[];
    onPlayGesture?: () => void;
    variants?: Record<string, string>;
    onGenerate?: (expressions: string[], usePrecise: boolean) => void;
  } = {},
) {
  return render(
    <CharacterChatExpressionMenu
      open
      onToggleOpen={() => {}}
      stageKind={stageKind}
      missingExpressions={options.missing ?? []}
      onPlayGesture={options.onPlayGesture ?? (() => {})}
      expressionPortraits={options.variants ?? {}}
      portraitAvailable
      preciseAvailable={false}
      onGenerateExpressions={options.onGenerate ?? (() => {})}
    />,
  );
}

describe("CharacterChatExpressionMenu", () => {
  it("previews an expression and a gesture on a 3D model", () => {
    const onPlayGesture = vi.fn();
    renderMenu("vrm", { onPlayGesture });
    fireEvent.click(button("うれしい"));
    expect(mocks.setExpressionPreview).toHaveBeenCalledWith("happy");
    fireEvent.click(button("手を振る"));
    expect(onPlayGesture).toHaveBeenCalledWith("wave_hand");
  });

  it("disables expressions the model does not provide", () => {
    renderMenu("vrm", { missing: ["surprised"] });
    expect(button("おどろき").disabled).toBe(true);
    expect(button("うれしい").disabled).toBe(false);
  });

  it("switches the camera framing and remembers it", () => {
    renderMenu("vrm");
    fireEvent.click(button("顔"));
    expect(button("顔").getAttribute("aria-pressed")).toBe("true");
    expect(localStorage.getItem("avatar_camera_framing")).toBe("face");
  });

  it("limits Live2D to its four expressions and has no gestures", () => {
    renderMenu("live2d");
    expect(button("かなしい").disabled).toBe(false);
    expect(button("リラックス").disabled).toBe(true);
    expect(button("手を振る").disabled).toBe(true);
    expect(button("顔").disabled).toBe(true);
  });

  it("clears the preview with the reset link", () => {
    mocks.expressionPreview = "angry";
    renderMenu("vrm");
    expect(button("おこる").getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(button("返答の表情に戻す"));
    expect(mocks.setExpressionPreview).toHaveBeenCalledWith(null);
  });

  it("on a 2D portrait, offers only drawn variants and draws the missing ones", () => {
    const onGenerate = vi.fn();
    renderMenu("portrait", {
      variants: { happy: "/api/x/happy.png" },
      onGenerate,
    });
    const chips = screen.getAllByRole("button", { name: /うれしい/ });
    // 表情を試すチップ(描いた表情だけ押せる)と、描く表情を選ぶチップの 2 つ
    expect(chips[0].hasAttribute("disabled")).toBe(false);
    expect(
      screen.getAllByRole<HTMLButtonElement>("button", { name: /かなしい/ })[0]
        .disabled,
    ).toBe(true);
    expect(button("手を振る").disabled).toBe(true);
    fireEvent.click(
      screen.getByRole("button", { name: /^選んだ表情を描く（4 枚）/ }),
    );
    expect(onGenerate).toHaveBeenCalledWith(
      ["sad", "angry", "surprised", "relaxed"],
      false,
    );
  });

  it("shows progress instead of the draw button while drawing", () => {
    mocks.expressionProgress = { expression: "sad", done: 1, total: 3 };
    renderMenu("portrait");
    expect(screen.getByText("「かなしい」を描いています（2/3）")).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: /選んだ表情を描く/ }),
    ).toBeNull();
  });
});
