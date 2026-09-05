import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { usePersistedState } from "./usePersistedState";

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => {
  cleanup();
});

describe("usePersistedState", () => {
  it("starts from the initial value and does not write it back", () => {
    const { result } = renderHook(() => usePersistedState("k", false));
    expect(result.current[0]).toBe(false);
    expect(localStorage.getItem("k")).toBeNull();
  });

  it("restores a stored JSON value and writes updates", () => {
    localStorage.setItem("k", "true");
    const { result } = renderHook(() => usePersistedState("k", false));
    expect(result.current[0]).toBe(true);
    act(() => {
      result.current[1](false);
    });
    expect(result.current[0]).toBe(false);
    expect(localStorage.getItem("k")).toBe("false");
  });

  it("supports functional updates", () => {
    const { result } = renderHook(() => usePersistedState("n", 1));
    act(() => {
      result.current[1]((prev) => prev + 1);
    });
    expect(result.current[0]).toBe(2);
    expect(localStorage.getItem("n")).toBe("2");
  });

  it("falls back to the initial value when the stored data is invalid", () => {
    localStorage.setItem("k", "{not json");
    const { result } = renderHook(() => usePersistedState("k", "init"));
    expect(result.current[0]).toBe("init");
  });

  it("uses custom serializers and sessionStorage", () => {
    sessionStorage.setItem("open", "1");
    const { result } = renderHook(() =>
      usePersistedState<boolean>("open", false, {
        storage: "session",
        serialize: (v) => (v ? "1" : "0"),
        deserialize: (raw) => raw === "1",
      }),
    );
    expect(result.current[0]).toBe(true);
    act(() => {
      result.current[1](false);
    });
    expect(sessionStorage.getItem("open")).toBe("0");
    expect(localStorage.getItem("open")).toBeNull();
  });

  it("accepts a lazy initializer", () => {
    const { result } = renderHook(() =>
      usePersistedState("lazy", () => ({ a: 1 })),
    );
    expect(result.current[0]).toEqual({ a: 1 });
  });
});
