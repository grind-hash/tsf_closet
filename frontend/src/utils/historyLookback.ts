import type { InstructionType } from "../types";

export type HistoryLookbackTargets = Record<InstructionType, boolean>;

export const DEFAULT_HISTORY_LOOKBACK_TARGETS: HistoryLookbackTargets = {
  action: true,
  conversation: true,
  dress_up: false,
  reality_alter: false,
};

export function normalizeHistoryLookbackTargets(
  value: unknown,
): HistoryLookbackTargets {
  if (!value || typeof value !== "object") {
    return { ...DEFAULT_HISTORY_LOOKBACK_TARGETS };
  }

  const saved = value as Partial<Record<InstructionType, unknown>>;
  return {
    action:
      typeof saved.action === "boolean"
        ? saved.action
        : DEFAULT_HISTORY_LOOKBACK_TARGETS.action,
    conversation:
      typeof saved.conversation === "boolean"
        ? saved.conversation
        : DEFAULT_HISTORY_LOOKBACK_TARGETS.conversation,
    dress_up:
      typeof saved.dress_up === "boolean"
        ? saved.dress_up
        : DEFAULT_HISTORY_LOOKBACK_TARGETS.dress_up,
    reality_alter:
      typeof saved.reality_alter === "boolean"
        ? saved.reality_alter
        : DEFAULT_HISTORY_LOOKBACK_TARGETS.reality_alter,
  };
}

export function isHistoryLookbackEnabled(
  targets: HistoryLookbackTargets,
  instructionType: InstructionType | string | undefined,
): boolean {
  if (!instructionType) {
    return DEFAULT_HISTORY_LOOKBACK_TARGETS.dress_up;
  }
  if (instructionType in targets) {
    return targets[instructionType as InstructionType];
  }
  return false;
}
