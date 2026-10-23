import { describe, expect, it } from "vitest";
import { findTextMatchRanges } from "./settingsSearchHighlight";
import { toSearchTerms } from "./settingsSearchIndex";

describe("findTextMatchRanges", () => {
  it("ひらがなの検索語で、カタカナの文字位置を返す", () => {
    expect(
      findTextMatchRanges("表示フォント", toSearchTerms("ふぉんと")),
    ).toEqual([[2, 6]]);
  });

  it("全角英字と大文字小文字の違いを無視する", () => {
    expect(findTextMatchRanges("ＶＲＭモデル", toSearchTerms("vrm"))).toEqual([
      [0, 3],
    ]);
  });

  it("複数の検索語の一致をそれぞれ返し、重なりはまとめる", () => {
    expect(
      findTextMatchRanges("履歴遡及件数と履歴", toSearchTerms("履歴 遡及")),
    ).toEqual([
      [0, 4],
      [7, 9],
    ]);
  });

  it("一致しなければ空配列を返す", () => {
    expect(findTextMatchRanges("難易度", toSearchTerms("フォント"))).toEqual(
      [],
    );
  });
});
