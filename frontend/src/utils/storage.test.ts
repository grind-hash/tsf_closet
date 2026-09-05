import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  readStorage,
  readStorageFlag,
  removeStorage,
  writeStorage,
  writeStorageFlag,
} from "./storage";

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("storage helpers", () => {
  it("reads and writes each storage kind separately", () => {
    expect(writeStorage("local", "k", "a")).toBe(true);
    expect(writeStorage("session", "k", "b")).toBe(true);
    expect(readStorage("local", "k")).toBe("a");
    expect(readStorage("session", "k")).toBe("b");
    removeStorage("local", "k");
    expect(readStorage("local", "k")).toBeNull();
    expect(readStorage("session", "k")).toBe("b");
  });

  it("treats only the string true as a set flag", () => {
    expect(readStorageFlag("local", "flag")).toBe(false);
    writeStorageFlag("local", "flag", true);
    expect(readStorageFlag("local", "flag")).toBe(true);
    writeStorageFlag("local", "flag", false);
    expect(readStorageFlag("local", "flag")).toBe(false);
    localStorage.setItem("flag", "1");
    expect(readStorageFlag("local", "flag")).toBe(false);
  });

  it("swallows storage errors", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(writeStorage("local", "k", "v")).toBe(false);
    expect(readStorage("local", "k")).toBeNull();
    expect(() => removeStorage("local", "k")).not.toThrow();
  });
});
