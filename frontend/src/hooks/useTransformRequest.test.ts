import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatProvider, useChat } from "../contexts/ChatContext";
import { writeStorageFlag } from "../utils/storage";
import { useTransformRequest } from "./useTransformRequest";

const mocks = vi.hoisted(() => ({
  settings: {
    state: {} as Record<string, unknown>,
    isNovelaiV5Active: false,
  },
}));

vi.mock("../contexts/SettingsContext", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../contexts/SettingsContext")>()),
  useSettings: () => mocks.settings,
}));

const REFERENCE = {
  enabled: true,
  imageData: "data:image/png;base64,AAAA",
  type: "character&style",
  strength: 1,
  fidelity: 1,
};

function setSettings({
  preciseReferences = [REFERENCE],
  isNovelaiV5Active = false,
  usagePercent = 100,
}: {
  preciseReferences?: (typeof REFERENCE)[];
  isNovelaiV5Active?: boolean;
  usagePercent?: number;
} = {}) {
  mocks.settings = {
    state: {
      imageProvider: "novelai",
      inpaintSettings: { i2iStrength: 0.5, inpaintNoise: 0 },
      inpaintMask: { maskDataUrl: null, selectedMaskId: null },
      inpaintEnabled: false,
      preciseReferences,
      anlasBalance: { usage: { percent: usagePercent, isNegative: false } },
    },
    isNovelaiV5Active,
  };
}

function renderRequest() {
  const onTransform = vi.fn();
  const hook = renderHook(
    () => ({ request: useTransformRequest(onTransform), chat: useChat() }),
    { wrapper: ChatProvider },
  );
  return { ...hook, onTransform };
}

/** GamePlayScreen と同じく、ユーザーメッセージと pending identity を積んでから送信する */
function send(
  current: ReturnType<typeof renderRequest>["result"]["current"],
  message: string,
  tempToken: string,
) {
  current.chat.addMessage({
    id: `user-${tempToken}`,
    sessionId: "session-1",
    role: "user",
    content: message,
    createdAt: "2026-10-18T00:00:00.000Z",
    pendingToken: tempToken,
  });
  current.chat.upsertPendingIdentity({
    tempToken,
    userMessageId: `user-${tempToken}`,
    feelingMessageId: null,
    resolvedHistoryId: null,
    status: "pending",
  });
  current.request.submitTransform(message, "action", false, tempToken);
}

/** onTransform の第6引数(pendingToken) */
const pendingTokenOf = (call: unknown[]) => call[5];

beforeEach(() => {
  sessionStorage.clear();
  setSettings();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("useTransformRequest", () => {
  it("passes the temp token when no confirmation is needed", () => {
    setSettings({ preciseReferences: [] });
    const { result, onTransform } = renderRequest();

    act(() => send(result.current, "walk", "token-1"));

    expect(onTransform).toHaveBeenCalledTimes(1);
    expect(pendingTokenOf(onTransform.mock.calls[0])).toBe("token-1");
  });

  it("keeps the temp token through the precise reference confirmation", () => {
    const { result, onTransform } = renderRequest();

    act(() => send(result.current, "walk", "token-2"));
    expect(onTransform).not.toHaveBeenCalled();
    expect(result.current.request.anlasConfirmPending?.anlasCost).toBe(5);

    act(() => result.current.request.handleAnlasConfirm(false));

    expect(onTransform).toHaveBeenCalledTimes(1);
    expect(pendingTokenOf(onTransform.mock.calls[0])).toBe("token-2");
  });

  it("passes the temp token when the precise reference warning is suppressed", () => {
    writeStorageFlag("session", "anlas_warn_suppressed", true);
    const { result, onTransform } = renderRequest();

    act(() => send(result.current, "walk", "token-3"));

    expect(result.current.request.anlasConfirmPending).toBeNull();
    expect(onTransform).toHaveBeenCalledTimes(1);
    expect(pendingTokenOf(onTransform.mock.calls[0])).toBe("token-3");
  });

  it("keeps the temp token through the V5 usage warning", () => {
    setSettings({ isNovelaiV5Active: true, usagePercent: 0 });
    const { result, onTransform } = renderRequest();

    act(() => send(result.current, "walk", "token-4"));
    expect(onTransform).not.toHaveBeenCalled();

    act(() => result.current.request.handleUsageWarnConfirm(false));

    expect(onTransform).toHaveBeenCalledTimes(1);
    expect(pendingTokenOf(onTransform.mock.calls[0])).toBe("token-4");
  });

  it("returns the message to the input when the precise reference confirmation is cancelled", () => {
    const { result, onTransform } = renderRequest();

    act(() => send(result.current, "walk to the park", "token-5"));
    expect(result.current.chat.state.messages).toHaveLength(1);

    act(() => result.current.request.handleAnlasCancel());

    expect(onTransform).not.toHaveBeenCalled();
    expect(result.current.request.anlasConfirmPending).toBeNull();
    expect(result.current.chat.state.messages).toHaveLength(0);
    expect(result.current.chat.state.pendingIdentities).toHaveLength(0);
    expect(result.current.chat.state.inputText).toBe("walk to the park");
  });

  it("returns the message to the input when the V5 usage warning is cancelled", () => {
    setSettings({ isNovelaiV5Active: true, usagePercent: 0 });
    const { result, onTransform } = renderRequest();

    act(() => send(result.current, "walk to the park", "token-6"));

    act(() => result.current.request.handleUsageWarnCancel());

    expect(onTransform).not.toHaveBeenCalled();
    expect(result.current.request.usageWarnPending).toBeNull();
    expect(result.current.chat.state.messages).toHaveLength(0);
    expect(result.current.chat.state.pendingIdentities).toHaveLength(0);
    expect(result.current.chat.state.inputText).toBe("walk to the park");
  });
});
