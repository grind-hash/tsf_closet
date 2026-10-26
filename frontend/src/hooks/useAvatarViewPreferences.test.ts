import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  AVATAR_FRAMING_KEY,
  AVATAR_LIGHTING_KEY,
  useAvatarFraming,
  useAvatarLighting,
} from "./useAvatarViewPreferences";

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
});

describe("useAvatarLighting", () => {
  it("defaults to the standard preset", () => {
    const { result } = renderHook(() => useAvatarLighting());
    expect(result.current[0]).toBe("standard");
  });

  it("restores a stored preset and ignores unknown values", () => {
    localStorage.setItem(AVATAR_LIGHTING_KEY, "night");
    const restored = renderHook(() => useAvatarLighting());
    expect(restored.result.current[0]).toBe("night");

    localStorage.setItem(AVATAR_LIGHTING_KEY, "disco");
    const invalid = renderHook(() => useAvatarLighting());
    expect(invalid.result.current[0]).toBe("standard");
  });

  it("shares updates between every mounted stage", () => {
    const first = renderHook(() => useAvatarLighting());
    const second = renderHook(() => useAvatarLighting());
    act(() => {
      first.result.current[1]("sunset");
    });
    expect(second.result.current[0]).toBe("sunset");
    expect(localStorage.getItem(AVATAR_LIGHTING_KEY)).toBe("sunset");
  });
});

describe("useAvatarFraming", () => {
  it("defaults to the upper-body framing and persists changes", () => {
    const { result } = renderHook(() => useAvatarFraming());
    expect(result.current[0]).toBe("upper");
    act(() => {
      result.current[1]("face");
    });
    expect(result.current[0]).toBe("face");
    expect(localStorage.getItem(AVATAR_FRAMING_KEY)).toBe("face");
  });
});
