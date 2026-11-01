import { describe, expect, it } from "vitest";
import { splitHintMarkers, stripHintMarkers } from "./hintMarkers";

describe("splitHintMarkers", () => {
  it("returns the whole text when there is no marker", () => {
    expect(splitHintMarkers("似合ってる。")).toEqual([
      { text: "似合ってる。", hint: false },
    ]);
  });

  it("separates the marked sentence", () => {
    expect(
      splitHintMarkers("いい色。〔頭に何か乗せたくなるかも。〕でも満足。"),
    ).toEqual([
      { text: "いい色。", hint: false },
      { text: "頭に何か乗せたくなるかも。", hint: true },
      { text: "でも満足。", hint: false },
    ]);
  });

  it("treats an unclosed marker as a hint up to the end while streaming", () => {
    expect(splitHintMarkers("いい色。〔頭に何か")).toEqual([
      { text: "いい色。", hint: false },
      { text: "頭に何か", hint: true },
    ]);
    expect(splitHintMarkers("いい色。〔")).toEqual([
      { text: "いい色。", hint: false },
    ]);
  });

  it("handles several marked parts and empty markers", () => {
    expect(splitHintMarkers("〔A〕B〔〕C〔D〕")).toEqual([
      { text: "A", hint: true },
      { text: "B", hint: false },
      { text: "C", hint: false },
      { text: "D", hint: true },
    ]);
  });
});

describe("stripHintMarkers", () => {
  it("removes only the markers", () => {
    expect(stripHintMarkers("いい色。〔頭に何か乗せたい。〕")).toBe(
      "いい色。頭に何か乗せたい。",
    );
  });
});
