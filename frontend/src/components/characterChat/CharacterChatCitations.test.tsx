import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import "../../i18n";
import CharacterChatCitations from "./CharacterChatCitations";
import { type LookupCitation, toLookupCitations } from "./lookupCitations";

afterEach(() => {
  cleanup();
});

function renderCitations(citations: LookupCitation[]) {
  return render(
    <MemoryRouter>
      <CharacterChatCitations citations={citations} />
    </MemoryRouter>,
  );
}

describe("CharacterChatCitations", () => {
  it("renders nothing without lookups", () => {
    const { container } = renderCitations([]);
    expect(container.innerHTML).toBe("");
  });

  it("shows only the kinds for legacy entries without text", () => {
    const { container } = renderCitations([
      {
        kind: "tendencies",
        query: null,
        text: null,
        sessionIds: [],
        sources: [],
      },
    ]);
    expect(screen.getByText("調べたこと: 傾向・統計")).toBeTruthy();
    expect(container.querySelector("details")).toBeNull();
  });

  it("opens the looked-up text and links session references to the gallery", () => {
    const { container } = renderCitations([
      {
        kind: "search_sessions",
        query: "元々男だったのに",
        text: [
          "「元々男だったのに」に一致するセッション(新しい順):",
          "- [913b92ab] 2026-08-11 はっしゅ: 元々男だったのに、…",
          "- [deadbeef] 2026-08-05 はっしゅ: (対応表に無い)",
        ].join("\n"),
        sessionIds: ["913b92ab-full-id"],
        sources: [],
      },
      {
        kind: "tendencies",
        query: null,
        text: "セッション総数: 3",
        sessionIds: [],
        sources: [],
      },
    ]);
    expect(
      screen.getByText(
        "調べたこと: 過去の検索「元々男だったのに」 / 傾向・統計",
      ),
    ).toBeTruthy();
    expect(container.querySelector("details")).not.toBeNull();
    expect(screen.getByText("検索語: 元々男だったのに")).toBeTruthy();
    const link = screen.getByRole("link", { name: "[913b92ab]" });
    expect(link.getAttribute("href")).toBe("/gallery/913b92ab-full-id");
    expect(screen.queryByRole("link", { name: "[deadbeef]" })).toBeNull();
    expect(screen.getByText("セッション総数: 3")).toBeTruthy();
  });

  it("shows the keywords sent to web search and opens sources in a new tab", () => {
    renderCitations([
      {
        kind: "web_search",
        query: "2026年9月 流行 ファッション",
        text: "検索結果の要約",
        sessionIds: [],
        sources: [
          { title: "秋の流行色", url: "https://example.com/trend" },
          { title: "news.example.org", url: "http://news.example.org/a" },
        ],
      },
      {
        kind: "weather",
        query: null,
        text: "東京: 晴れ 24℃",
        sessionIds: [],
        sources: [],
      },
    ]);
    expect(
      screen.getByText(
        "調べたこと: Web検索「2026年9月 流行 ファッション」 / 天気",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText("Web検索に送った語: 2026年9月 流行 ファッション"),
    ).toBeTruthy();
    expect(screen.queryByText(/^検索語:/)).toBeNull();
    expect(screen.getByText("出典")).toBeTruthy();

    const link = screen.getByRole("link", { name: "秋の流行色" });
    expect(link.getAttribute("href")).toBe("https://example.com/trend");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    const hostLink = screen.getByRole("link", { name: "news.example.org" });
    expect(hostLink.getAttribute("href")).toBe("http://news.example.org/a");
    expect(hostLink.getAttribute("rel")).toBe("noopener noreferrer");

    expect(screen.getByText("東京: 晴れ 24℃")).toBeTruthy();
    expect(screen.getAllByRole("link")).toHaveLength(2);
  });

  it("never renders links for unsafe source urls", () => {
    renderCitations(
      toLookupCitations({
        lookups: [
          {
            kind: "web_search",
            query: "サクラ 新作",
            text: "検索結果の要約",
            session_ids: [],
            sources: [
              { title: "bad", url: "javascript:alert(1)" },
              { title: "good", url: "https://example.com/a" },
            ],
          },
        ],
      }),
    );
    expect(screen.queryByRole("link", { name: "bad" })).toBeNull();
    expect(
      screen.getByRole("link", { name: "good" }).getAttribute("href"),
    ).toBe("https://example.com/a");
  });

  it("shows the keywords that were not sent when a web search was skipped", () => {
    const note =
      "(検索サービス Tavily の利用規約で禁止されている内容のため、検索しませんでした)";
    renderCitations(
      toLookupCitations({
        lookups: [
          {
            kind: "web_search",
            query: "AV女優 人気",
            text: note,
            session_ids: [],
            sources: [],
            refused: "search_policy",
          },
        ],
      }),
    );
    expect(
      screen.getByText(
        "調べたこと: Web検索（利用規約により見送り）「AV女優 人気」",
      ),
    ).toBeTruthy();
    expect(screen.getByText("送らなかった検索語: AV女優 人気")).toBeTruthy();
    expect(screen.queryByText(/Web検索に送った語/)).toBeNull();
    expect(screen.getByText(note)).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
  });
});
