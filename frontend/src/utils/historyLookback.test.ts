import { describe, expect, it } from "vitest";
import {
  DEFAULT_HISTORY_LOOKBACK_TARGETS,
  isHistoryLookbackEnabled,
  normalizeHistoryLookbackTargets,
} from "./historyLookback";

describe("history lookback targets", () => {
  it("uses backward-compatible defaults", () => {
    expect(DEFAULT_HISTORY_LOOKBACK_TARGETS).toEqual({
      action: true,
      conversation: true,
      dress_up: false,
      reality_alter: false,
    });
  });

  it("fills missing localStorage values with defaults", () => {
    expect(normalizeHistoryLookbackTargets({ dress_up: true })).toEqual({
      action: true,
      conversation: true,
      dress_up: true,
      reality_alter: false,
    });
  });

  it("resolves every instruction type from the selected targets", () => {
    const targets = {
      action: false,
      conversation: true,
      dress_up: true,
      reality_alter: false,
    };

    expect(isHistoryLookbackEnabled(targets, "action")).toBe(false);
    expect(isHistoryLookbackEnabled(targets, "conversation")).toBe(true);
    expect(isHistoryLookbackEnabled(targets, "dress_up")).toBe(true);
    expect(isHistoryLookbackEnabled(targets, "reality_alter")).toBe(false);
  });
});
