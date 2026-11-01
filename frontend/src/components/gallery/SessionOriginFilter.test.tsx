import {
  act,
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "../../i18n";
import { useSessionOriginFilter } from "../../hooks/useSessionOriginFilter";
import i18n from "../../i18n";
import SessionOriginFilter from "./SessionOriginFilter";

afterEach(cleanup);

describe("SessionOriginFilter", () => {
  it("shows the three filters with counts and marks the selected one", async () => {
    await i18n.changeLanguage("ja");
    const onChange = vi.fn();
    render(
      <SessionOriginFilter
        value="play"
        counts={{ all: 5, play: 3, salon: 2 }}
        onChange={onChange}
      />,
    );

    const salon = screen.getByRole("button", { name: /サロン経営/ });
    expect(salon.textContent).toContain("2");
    expect(
      screen
        .getByRole("button", { name: /通常プレイ/ })
        .getAttribute("aria-pressed"),
    ).toBe("true");
    expect(salon.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(salon);
    expect(onChange).toHaveBeenCalledWith("salon");
  });
});

describe("useSessionOriginFilter", () => {
  it("restores the last selection per scope when reopened", () => {
    const first = renderHook(() => useSessionOriginFilter("test-gallery"));
    expect(first.result.current[0]).toBe("all");
    act(() => first.result.current[1]("salon"));
    first.unmount();

    const reopened = renderHook(() => useSessionOriginFilter("test-gallery"));
    const other = renderHook(() => useSessionOriginFilter("test-picker"));

    expect(reopened.result.current[0]).toBe("salon");
    expect(other.result.current[0]).toBe("all");
  });
});
