import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import "../../i18n";
import CharacterChatCitations from "./CharacterChatCitations";
import type { LookupCitation } from "./lookupCitations";

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
      { kind: "tendencies", query: null, text: null, sessionIds: [] },
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
      },
      {
        kind: "tendencies",
        query: null,
        text: "セッション総数: 3",
        sessionIds: [],
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
});
