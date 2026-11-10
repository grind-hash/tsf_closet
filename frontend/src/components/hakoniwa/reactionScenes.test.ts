import { describe, expect, it } from "vitest";
import { reactionScenes } from "./reactionScenes";

const areas = new Map([
  ["a", "living"],
  ["b", "garden"],
  ["c", "living"],
]);

describe("reactionScenes", () => {
  it("keeps everyone in one scene when they share a place", () => {
    const scenes = reactionScenes(
      [
        { resident_id: "a", text: "1" },
        { resident_id: "c", text: "2" },
      ],
      areas,
      "living",
      "living",
    );
    expect(scenes).toEqual([
      {
        area: "living",
        lines: [
          { resident_id: "a", text: "1" },
          { resident_id: "c", text: "2" },
        ],
      },
    ]);
  });

  it("splits speakers in other places and plays the viewed place last", () => {
    const scenes = reactionScenes(
      [
        { resident_id: "a", text: "1" },
        { resident_id: "b", text: "2" },
      ],
      areas,
      "living",
      "living",
    );
    expect(scenes.map((scene) => scene.area)).toEqual(["garden", "living"]);
    expect(scenes[0].lines).toEqual([{ resident_id: "b", text: "2" }]);
    expect(scenes[1].lines).toEqual([{ resident_id: "a", text: "1" }]);
  });

  it("keeps line order when nobody is in the viewed place", () => {
    const scenes = reactionScenes(
      [
        { resident_id: "b", text: "1" },
        { resident_id: "a", text: "2" },
      ],
      areas,
      "study",
      "study",
    );
    expect(scenes.map((scene) => scene.area)).toEqual(["garden", "living"]);
  });

  it("uses the fallback place for an unknown speaker", () => {
    const scenes = reactionScenes(
      [{ resident_id: "x", text: "1" }],
      areas,
      "living",
      "garden",
    );
    expect(scenes).toEqual([
      { area: "garden", lines: [{ resident_id: "x", text: "1" }] },
    ]);
  });
});
