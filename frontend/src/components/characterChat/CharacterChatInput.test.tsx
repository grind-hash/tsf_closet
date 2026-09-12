import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "../../i18n";
import CharacterChatInput from "./CharacterChatInput";

const speech = {
  supported: false,
  listening: false,
  autoSend: false,
  error: null,
  onToggleListening: () => {},
  onToggleAutoSend: () => {},
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderInput({
  value = "こんにちは",
  busy = false,
  pointerFine = true,
}: {
  value?: string;
  busy?: boolean;
  pointerFine?: boolean;
} = {}) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: pointerFine })),
  );
  const onSubmit = vi.fn();
  render(
    <CharacterChatInput
      value={value}
      onChange={() => {}}
      onSubmit={onSubmit}
      name="サクラ"
      busy={busy}
      speech={speech}
    />,
  );
  return { field: screen.getByRole("textbox"), onSubmit };
}

describe("CharacterChatInput", () => {
  it("uses a multi-line field", () => {
    const { field } = renderInput();
    expect(field.tagName).toBe("TEXTAREA");
  });

  it("sends on Enter", () => {
    const { field, onSubmit } = renderInput();
    const notPrevented = fireEvent.keyDown(field, { key: "Enter" });
    expect(notPrevented).toBe(false);
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("leaves Shift+Enter to insert a newline", () => {
    const { field, onSubmit } = renderInput();
    const notPrevented = fireEvent.keyDown(field, {
      key: "Enter",
      shiftKey: true,
    });
    expect(notPrevented).toBe(true);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("does not send the Enter that confirms IME conversion", () => {
    const { field, onSubmit } = renderInput();
    const notPrevented = fireEvent.keyDown(field, {
      key: "Enter",
      isComposing: true,
    });
    expect(notPrevented).toBe(true);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("swallows Enter without sending while busy or empty", () => {
    const busy = renderInput({ busy: true });
    expect(fireEvent.keyDown(busy.field, { key: "Enter" })).toBe(false);
    expect(busy.onSubmit).not.toHaveBeenCalled();
    cleanup();

    const empty = renderInput({ value: "   " });
    expect(fireEvent.keyDown(empty.field, { key: "Enter" })).toBe(false);
    expect(empty.onSubmit).not.toHaveBeenCalled();
  });

  it("treats Enter as a newline on touch devices", () => {
    const { field, onSubmit } = renderInput({ pointerFine: false });
    const notPrevented = fireEvent.keyDown(field, { key: "Enter" });
    expect(notPrevented).toBe(true);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
