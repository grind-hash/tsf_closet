import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "../../i18n";
import AdventureFreeInput from "./AdventureFreeInput";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderInput(busy = false) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: true })),
  );
  const onSubmit = vi.fn();
  render(
    <AdventureFreeInput
      value="扉を開ける"
      onChange={() => {}}
      onSubmit={onSubmit}
      busy={busy}
    />,
  );
  return { field: screen.getByRole("textbox"), onSubmit };
}

describe("AdventureFreeInput", () => {
  it("uses a multi-line field that sends on Enter", () => {
    const { field, onSubmit } = renderInput();
    expect(field.tagName).toBe("TEXTAREA");
    expect(fireEvent.keyDown(field, { key: "Enter" })).toBe(false);
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("leaves Shift+Enter to insert a newline", () => {
    const { field, onSubmit } = renderInput();
    expect(fireEvent.keyDown(field, { key: "Enter", shiftKey: true })).toBe(
      true,
    );
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("does not send on Enter while the turn is streaming", () => {
    const { field, onSubmit } = renderInput(true);
    expect(fireEvent.keyDown(field, { key: "Enter" })).toBe(false);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
