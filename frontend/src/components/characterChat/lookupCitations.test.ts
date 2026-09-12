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
      {
        kind: "tendencies",
        query: null,
        text: null,
        sessionIds: [],
        sources: [],
      },
      {
        kind: "search_sessions",
        query: "元々男だったのに",
        text: "「元々男だったのに」に一致するセッション(新しい順):\n- [913b92ab] ...",
        sessionIds: ["913b92ab0000", "1c44f2d50000"],
        sources: [],
      },
    ]);
  });

  it("keeps only http(s) web search sources and falls back to the host for empty titles", () => {
    const citations = toLookupCitations({
      lookups: [
        {
          kind: "web_search",
          query: " 2026年9月 流行 ファッション ",
          session_id: null,
          text: "検索結果:\n- 秋の流行色 ...",
          session_ids: [],
          sources: [
            { title: " 秋の流行色 ", url: "https://example.com/trend" },
            { title: "", url: "http://news.example.org/a" },
            { title: "script", url: "javascript:alert(1)" },
            { title: "file", url: "ftp://example.com/file" },
            { title: "broken", url: "not a url" },
            { title: "relative", url: "/relative/path" },
            { title: "no url" },
            { title: "duplicate", url: "https://example.com/trend" },
          ],
        },
      ],
    });
    expect(citations).toEqual([
      {
        kind: "web_search",
        query: "2026年9月 流行 ファッション",
        text: "検索結果:\n- 秋の流行色 ...",
        sessionIds: [],
        sources: [
          { title: "秋の流行色", url: "https://example.com/trend" },
          { title: "news.example.org", url: "http://news.example.org/a" },
        ],
      },
    ]);
  });

  it("normalizes weather lookups without a query or sources", () => {
    const citations = toLookupCitations({
      lookups: [
        {
          kind: "weather",
          query: null,
          session_id: null,
          text: "東京: 晴れ 24℃",
          session_ids: [],
        },
        "weather",
      ],
    });
    expect(citations).toEqual([
      {
        kind: "weather",
        query: null,
        text: "東京: 晴れ 24℃",
        sessionIds: [],
        sources: [],
      },
      { kind: "weather", query: null, text: null, sessionIds: [], sources: [] },
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
