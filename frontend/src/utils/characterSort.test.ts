import { describe, expect, it } from "vitest";
import { isCharacterSortOrder, sortCharacterPresets } from "./characterSort";

const presets = [
  { id: "b", name: "ユウ", created_at: "2026-10-03T09:00:00" },
  { id: "a", name: "サクラ", created_at: "2026-10-05T09:00:00" },
  { id: "c", name: "アオイ", created_at: "2026-10-01T09:00:00" },
];

const ids = (items: readonly { id: string }[]) => items.map((item) => item.id);

describe("sortCharacterPresets", () => {
  it("作成日の新しい順・古い順に並べる", () => {
    expect(ids(sortCharacterPresets(presets, "created_desc", "ja"))).toEqual([
      "a",
      "b",
      "c",
    ]);
    expect(ids(sortCharacterPresets(presets, "created_asc", "ja"))).toEqual([
      "c",
      "b",
      "a",
    ]);
  });

  it("名前の昇順・降順に並べる", () => {
    expect(ids(sortCharacterPresets(presets, "name_asc", "ja"))).toEqual([
      "c",
      "a",
      "b",
    ]);
    expect(ids(sortCharacterPresets(presets, "name_desc", "ja"))).toEqual([
      "b",
      "a",
      "c",
    ]);
  });

  it("名前の数字は数の大きさで比べる", () => {
    const numbered = [
      { id: "x", name: "キャラ10", created_at: "2026-10-01T09:00:00" },
      { id: "y", name: "キャラ2", created_at: "2026-10-01T09:00:00" },
    ];
    expect(ids(sortCharacterPresets(numbered, "name_asc", "ja"))).toEqual([
      "y",
      "x",
    ]);
  });

  it("同順位は id で決め、元の配列は変えない", () => {
    const tied = [
      { id: "q", name: "サクラ", created_at: "2026-10-01T09:00:00" },
      { id: "p", name: "サクラ", created_at: "2026-10-01T09:00:00" },
    ];
    expect(ids(sortCharacterPresets(tied, "created_desc", "ja"))).toEqual([
      "p",
      "q",
    ]);
    expect(ids(sortCharacterPresets(tied, "name_desc", "ja"))).toEqual([
      "p",
      "q",
    ]);
    expect(ids(tied)).toEqual(["q", "p"]);
  });
});

describe("isCharacterSortOrder", () => {
  it("決められた4つの並び順だけを受け付ける", () => {
    expect(isCharacterSortOrder("created_desc")).toBe(true);
    expect(isCharacterSortOrder("name_asc")).toBe(true);
    expect(isCharacterSortOrder("updated_desc")).toBe(false);
    expect(isCharacterSortOrder(null)).toBe(false);
  });
});
