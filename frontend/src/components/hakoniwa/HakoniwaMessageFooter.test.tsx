import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "../../i18n";
import type { HakoniwaWebSearch } from "../../apis/hakoniwa";
import HakoniwaMessageFooter from "./HakoniwaMessageFooter";

afterEach(cleanup);

const search: HakoniwaWebSearch = {
  query: "科学 最新",
  retrieved_at: "2026-11-14T03:00:00+00:00",
  status: "used",
  sources: [{ title: "科学の記事", url: "https://example.com/news" }],
};

describe("HakoniwaMessageFooter", () => {
  it("旧データと検索なしの会話にも注記を表示する", () => {
    render(<HakoniwaMessageFooter />);
    expect(
      screen.getByText(/TSF Closetおよび作者の見解ではありません/),
    ).toBeTruthy();
    expect(screen.queryByText("参照した情報")).toBeNull();
  });

  it("出典を折りたたみ、危険なURLと重複を表示しない", () => {
    const { container } = render(
      <HakoniwaMessageFooter
        search={{
          ...search,
          sources: [
            ...search.sources,
            ...search.sources,
            { title: "危険", url: "javascript:alert(1)" },
          ],
        }}
      />,
    );
    const details = container.querySelector("details");
    expect(details?.open).toBe(false);
    fireEvent.click(screen.getByText("参照した情報"));
    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(
      screen.getByRole("link", { name: "科学の記事" }).getAttribute("rel"),
    ).toContain("noopener");
    expect(screen.getByText("検索語: 科学 最新")).toBeTruthy();
  });

  it.each([
    "failed",
    "no_results",
    "blocked",
    "unused",
  ] as const)("%sでは検索を利用した出典として表示しない", (status) => {
    const { container } = render(
      <HakoniwaMessageFooter search={{ ...search, status }} />,
    );
    expect(
      container.querySelector(".hakoniwa-message-footer__status"),
    ).not.toBeNull();
    expect(screen.queryByText("参照した情報")).toBeNull();
  });

  it("出典のクリックとキー操作を幕送りへ伝えない", () => {
    const advance = vi.fn();
    render(
      <div onClick={advance} onKeyDown={advance}>
        <HakoniwaMessageFooter search={search} />
      </div>,
    );
    const summary = screen.getByText("参照した情報");
    fireEvent.click(summary);
    fireEvent.keyDown(summary, { key: "Enter" });
    expect(advance).not.toHaveBeenCalled();
    fireEvent.keyDown(summary, { key: "Escape" });
    expect(advance).toHaveBeenCalledOnce();
  });
});
