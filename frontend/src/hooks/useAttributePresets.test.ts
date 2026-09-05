import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AttributePreset } from "../types";
import {
  ATTRIBUTE_PRESET_STORAGE_KEY,
  loadPresetAttributes,
  resetAttributePresetCache,
  useAttributePresets,
} from "./useAttributePresets";

beforeEach(() => {
  localStorage.clear();
  resetAttributePresetCache();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("useAttributePresets", () => {
  it("reads existing presets from localStorage", () => {
    localStorage.setItem(
      ATTRIBUTE_PRESET_STORAGE_KEY,
      JSON.stringify([
        { id: "1", name: "a", attributes: ["x"], createdAt: "2026-01-01" },
      ]),
    );
    resetAttributePresetCache();
    const { result } = renderHook(() => useAttributePresets());
    expect(result.current.presets).toHaveLength(1);
    expect(result.current.presets[0].name).toBe("a");
  });

  it("saves a preset, persists it and updates every subscriber", () => {
    const first = renderHook(() => useAttributePresets());
    const second = renderHook(() => useAttributePresets());

    const outcome: { saved: AttributePreset | null } = { saved: null };
    act(() => {
      outcome.saved = first.result.current.savePreset("  outfit ", [
        "red",
        "hat",
      ]);
    });

    expect(outcome.saved).not.toBeNull();
    expect(outcome.saved?.name).toBe("outfit");
    expect(outcome.saved?.attributes).toEqual(["red", "hat"]);
    expect(first.result.current.presets).toHaveLength(1);
    expect(second.result.current.presets).toHaveLength(1);
    expect(
      JSON.parse(localStorage.getItem(ATTRIBUTE_PRESET_STORAGE_KEY) ?? "[]"),
    ).toHaveLength(1);
  });

  it("refuses an empty name or empty attributes", () => {
    const { result } = renderHook(() => useAttributePresets());
    let a: unknown = "unset";
    let b: unknown = "unset";
    act(() => {
      a = result.current.savePreset("   ", ["x"]);
      b = result.current.savePreset("name", []);
    });
    expect(a).toBeNull();
    expect(b).toBeNull();
    expect(result.current.presets).toHaveLength(0);
  });

  it("deletes a preset by id", () => {
    const { result } = renderHook(() => useAttributePresets());
    act(() => {
      result.current.savePreset("one", ["x"]);
    });
    const id = result.current.presets[0].id;
    act(() => {
      result.current.deletePreset(id);
    });
    expect(result.current.presets).toHaveLength(0);
    expect(localStorage.getItem(ATTRIBUTE_PRESET_STORAGE_KEY)).toBe("[]");
  });

  it("picks up changes made in another tab via the storage event", () => {
    const { result } = renderHook(() => useAttributePresets());
    expect(result.current.presets).toHaveLength(0);
    localStorage.setItem(
      ATTRIBUTE_PRESET_STORAGE_KEY,
      JSON.stringify([
        { id: "9", name: "remote", attributes: ["y"], createdAt: "" },
      ]),
    );
    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", { key: ATTRIBUTE_PRESET_STORAGE_KEY }),
      );
    });
    expect(result.current.presets.map((p) => p.name)).toEqual(["remote"]);
  });
});

describe("loadPresetAttributes", () => {
  it("adds every attribute in order and keeps going after a failure", async () => {
    const calls: string[] = [];
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const addAttribute = vi.fn(async (text: string) => {
      calls.push(text);
      if (text === "b") throw new Error("boom");
    });
    await loadPresetAttributes(
      { id: "1", name: "p", attributes: ["a", "b", "c"], createdAt: "" },
      addAttribute,
    );
    expect(calls).toEqual(["a", "b", "c"]);
    expect(errorSpy).toHaveBeenCalledTimes(1);
  });
});
