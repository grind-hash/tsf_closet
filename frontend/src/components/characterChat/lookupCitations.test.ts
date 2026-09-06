// @vitest-environment node
import { describe, expect, it } from "vitest";
import { sessionIdByPrefix, toLookupCitations } from "./lookupCitations";

describe("toLookupCitations", () => {
  it("accepts legacy kind strings and detail objects together", () => {
    const citations = toLookupCitations({
      lookups: [
        "tendencies",
        "bogus",
        {
          kind: "search_sessions",
          query: " 元々男だったのに ",
          text: "「元々男だったのに」に一致するセッション(新しい順):\n- [913b92ab] ...",
          session_ids: ["913b92ab0000", "", "1c44f2d50000"],
        },
        { kind: "unknown", text: "x" },
      ],
    });
    expect(citations).toEqual([
      { kind: "tendencies", query: null, text: null, sessionIds: [] },
      {
        kind: "search_sessions",
        query: "元々男だったのに",
        text: "「元々男だったのに」に一致するセッション(新しい順):\n- [913b92ab] ...",
        sessionIds: ["913b92ab0000", "1c44f2d50000"],
      },
    ]);
  });

  it("returns an empty list when meta has no lookups", () => {
    expect(toLookupCitations(undefined)).toEqual([]);
    expect(toLookupCitations({})).toEqual([]);
    expect(toLookupCitations({ lookups: [] })).toEqual([]);
  });
});

describe("sessionIdByPrefix", () => {
  it("maps the first eight characters to the full id", () => {
    const map = sessionIdByPrefix(["913b92ab-full", "1c44f2d5-full"]);
    expect(map.get("913b92ab")).toBe("913b92ab-full");
    expect(map.get("1c44f2d5")).toBe("1c44f2d5-full");
    expect(map.get("00000000")).toBeUndefined();
  });
});
