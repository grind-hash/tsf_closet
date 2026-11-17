import { describe, expect, it } from "vitest";
import type { HakoniwaEvent } from "../../apis/hakoniwa";
import { advLogScenes, advScript } from "./advLog";

function event(id: string, continues?: string): HakoniwaEvent {
  return {
    id,
    title: `title ${id}`,
    narration: `narration ${id}`,
    lines: [
      { speaker: "sakura", text: `first ${id}` },
      { speaker: "kenta", text: `second ${id}` },
    ],
    continues,
  } as HakoniwaEvent;
}

const first = event("a");
const second = event("b", "a");
const third = event("c", "b");
const other = event("x");
const all = [first, other, second, third];

describe("advScript", () => {
  it("puts the narration before the lines", () => {
    expect(advScript(first)).toEqual([
      { speaker: null, text: "narration a" },
      { speaker: "sakura", text: "first a" },
      { speaker: "kenta", text: "second a" },
    ]);
  });
});

describe("advLogScenes", () => {
  it("shows the open scene up to the current step", () => {
    const scenes = advLogScenes(all, "a", 1);

    expect(scenes).toHaveLength(1);
    expect(scenes[0].lines.map((line) => line.text)).toEqual([
      "narration a",
      "first a",
    ]);
  });

  it("goes back through continued scenes, oldest first", () => {
    const scenes = advLogScenes(all, "c", 0);

    expect(scenes.map((scene) => scene.event.id)).toEqual(["a", "b", "c"]);
    // 前の場面は全文、いまの場面は読み終えた幕まで
    expect(scenes[0].lines).toHaveLength(3);
    expect(scenes[1].lines).toHaveLength(3);
    expect(scenes[2].lines.map((line) => line.text)).toEqual(["narration c"]);
  });

  it("stops when the source scene is gone or the chain loops", () => {
    const orphan = event("o", "missing");
    const loopA = event("la", "lb");
    const loopB = event("lb", "la");

    expect(advLogScenes([orphan], "o", 9)).toHaveLength(1);
    expect(
      advLogScenes([loopA, loopB], "la", 0).map((scene) => scene.event.id),
    ).toEqual(["lb", "la"]);
    expect(advLogScenes(all, "nope", 0)).toEqual([]);
  });
});
