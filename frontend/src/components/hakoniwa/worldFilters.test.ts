import { describe, expect, it } from "vitest";
import type { HakoniwaWorldSummary } from "../../apis/hakoniwa";
import { ALL_WORLDS, filterWorlds, worldFacetCounts } from "./worldFilters";

function world(
  id: string,
  presence: "known" | "hidden" | undefined,
  names: string[],
): HakoniwaWorldSummary {
  return {
    id,
    name: id,
    day: 1,
    resident_count: names.length,
    event_count: 0,
    created_at: null,
    updated_at: null,
    residents: names
      .slice(0, 2)
      .map((name) => ({ id: name, name, avatar_url: null })),
    player_presence: presence,
    resident_names: names,
  };
}

const WORLDS = [
  world("a", "known", ["高瀬 葵", "苑田 蓮", "森下 栞"]),
  world("b", "hidden", ["高瀬 葵", "九条 薫"]),
  world("c", undefined, ["苑田 蓮"]),
];

describe("worldFilters", () => {
  it("住民とあなた・住民の両方で絞り込む(値の無い世界は顔なじみ)", () => {
    expect(filterWorlds(WORLDS, ALL_WORLDS).map((item) => item.id)).toEqual([
      "a",
      "b",
      "c",
    ]);
    expect(
      filterWorlds(WORLDS, { presence: "known", resident: null }).map(
        (item) => item.id,
      ),
    ).toEqual(["a", "c"]);
    // 顔は先頭2人だけでも、名前は全員ぶんで絞り込む
    expect(
      filterWorlds(WORLDS, { presence: "all", resident: "森下 栞" }).map(
        (item) => item.id,
      ),
    ).toEqual(["a"]);
    expect(
      filterWorlds(WORLDS, { presence: "hidden", resident: "苑田 蓮" }),
    ).toEqual([]);
  });

  it("件数は、もう片方の絞り込みを効かせて数える", () => {
    const all = worldFacetCounts(WORLDS, ALL_WORLDS);
    expect(all.presence).toEqual({ all: 3, known: 2, hidden: 1 });
    expect(all.residents.slice(0, 2)).toEqual([
      { name: "苑田 蓮", count: 2 },
      { name: "高瀬 葵", count: 2 },
    ]);

    const hidden = worldFacetCounts(WORLDS, {
      presence: "hidden",
      resident: "高瀬 葵",
    });
    // 住民とあなたの件数は「高瀬 葵」のいる世界の中で、住民の件数は見えない存在の世界の中で
    expect(hidden.presence).toEqual({ all: 2, known: 1, hidden: 1 });
    expect(hidden.residents).toEqual([
      { name: "九条 薫", count: 1 },
      { name: "高瀬 葵", count: 1 },
    ]);
  });
});
