import { describe, expect, it } from "vitest";
import {
  currentActivity,
  type HakoniwaActivityInput,
} from "./hakoniwaActivity";

const idle: HakoniwaActivityInput = {
  busy: null,
  lookTarget: null,
  lookProgress: null,
  avatarBatch: null,
  eventProgress: null,
};

describe("currentActivity", () => {
  it("shows nothing while idle or during quick operations", () => {
    expect(currentActivity(idle)).toBeNull();
    for (const busy of ["settings", "furniture", "rule", "chat"] as const) {
      expect(currentActivity({ ...idle, busy })).toBeNull();
    }
  });

  it("names the long-running operations", () => {
    expect(currentActivity({ ...idle, busy: "day" })).toEqual({ kind: "day" });
    expect(currentActivity({ ...idle, busy: "transform" })).toEqual({
      kind: "transform",
    });
    expect(currentActivity({ ...idle, busy: "reality" })).toEqual({
      kind: "reality",
    });
    expect(currentActivity({ ...idle, busy: "scene" })).toEqual({
      kind: "scene",
    });
  });

  it("follows the phases of an event", () => {
    const event = { ...idle, busy: "event" as const };
    expect(currentActivity(event)).toEqual({ kind: "eventWriting" });
    expect(
      currentActivity({
        ...event,
        eventProgress: { phase: "planning", done: 0, total: 0 },
      }),
    ).toEqual({ kind: "eventPlanning" });
    expect(
      currentActivity({
        ...event,
        eventProgress: { phase: "portraits", done: 1, total: 2 },
      }),
    ).toEqual({ kind: "eventPortraits", done: 1, total: 2 });
    expect(
      currentActivity({
        ...event,
        eventProgress: { phase: "scene", done: 0, total: 0 },
      }),
    ).toEqual({ kind: "eventScene" });
  });

  it("counts portraits generated one by one", () => {
    expect(currentActivity({ ...idle, busy: "avatar" })).toEqual({
      kind: "avatar",
    });
    expect(
      currentActivity({
        ...idle,
        busy: "avatar",
        avatarBatch: { done: 2, total: 5 },
      }),
    ).toEqual({ kind: "avatarBatch", done: 2, total: 5 });
  });

  it("counts looks and tells the memo check apart", () => {
    expect(
      currentActivity({
        ...idle,
        busy: "look",
        lookTarget: "memo",
        lookProgress: { target: "memo", done: 3, total: 5 },
      }),
    ).toEqual({ kind: "look", lookTarget: "memo", done: 3, total: 5 });
    expect(
      currentActivity({ ...idle, busy: "look", lookTarget: "memo" }),
    ).toEqual({ kind: "memoPlanning" });
    expect(currentActivity({ ...idle, busy: "look" })).toBeNull();
  });
});
