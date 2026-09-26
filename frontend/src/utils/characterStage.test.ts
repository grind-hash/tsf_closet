import { describe, expect, it } from "vitest";
import type { SessionCharacter } from "../types";
import {
  countOnStage,
  getStageLimit,
  overflowCharacterIds,
  sortRoster,
} from "./characterStage";

function character(
  id: string,
  slotIndex: number,
  overrides: Partial<SessionCharacter> = {},
): SessionCharacter {
  return {
    id,
    session_id: "sess-1",
    slot_index: slotIndex,
    name: id,
    appearance_natural: "",
    appearance_tags: "",
    position: "center",
    is_protagonist: false,
    appearance_lock: false,
    exclude_from_effects: false,
    source_preset_id: null,
    negative_tags: "",
    profile: null,
    on_stage: true,
    thumbnail_url: null,
    created_at: "",
    updated_at: "",
    ...overrides,
  };
}

describe("characterStage", () => {
  it("主人公を先頭に slot 順で並べる", () => {
    const sorted = sortRoster([
      character("b", 2),
      character("hero", 0, { is_protagonist: true }),
      character("a", 1),
    ]);
    expect(sorted.map((c) => c.id)).toEqual(["hero", "a", "b"]);
  });

  it("登場人数は主人公＋登場 ON の人物で数え、主人公が未登録でも 1 人と数える", () => {
    const cast = [character("a", 1), character("b", 2, { on_stage: false })];
    expect(countOnStage(cast)).toBe(2);
    expect(
      countOnStage([
        character("hero", 0, { is_protagonist: true, on_stage: false }),
        ...cast,
      ]),
    ).toBe(2);
  });

  it("画像モデルごとの上限を返す", () => {
    expect(getStageLimit(false)).toBe(6);
    expect(getStageLimit(true)).toBe(22);
  });

  it("上限を超えた分を並び順の後ろから外す（登場 OFF は数えない）", () => {
    const cast = [
      character("hero", 0, { is_protagonist: true }),
      character("a", 1),
      character("off", 2, { on_stage: false }),
      character("b", 3),
      character("c", 4),
    ];
    expect([...overflowCharacterIds(cast, 3)]).toEqual(["c"]);
    expect(overflowCharacterIds(cast, 6).size).toBe(0);
  });
});
