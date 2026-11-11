import { describe, expect, it } from "vitest";
import type { HakoniwaResident } from "../../apis/hakoniwa";
import {
  canContinueEvent,
  chosenPartners,
  maleBodyPairs,
  roomMates,
  togglePartner,
} from "./eventCast";

function resident(
  id: string,
  area: string,
  bodyGender: "female" | "male",
): HakoniwaResident {
  return {
    id,
    current_area: area,
    body_gender: bodyGender,
  } as HakoniwaResident;
}

const sakura = resident("sakura", "living", "female");
const kenta = resident("kenta", "living", "male");
const daiki = resident("daiki", "garden", "male");
const yui = resident("yui", "living", "female");
const all = [sakura, kenta, daiki, yui];

describe("roomMates", () => {
  it("lists the others in the same room", () => {
    expect(roomMates(all, sakura).map((item) => item.id)).toEqual([
      "kenta",
      "yui",
    ]);
    expect(roomMates(all, daiki)).toEqual([]);
  });
});

describe("chosenPartners", () => {
  it("skips the target, duplicates and missing ids and keeps the order", () => {
    const picked = chosenPartners(all, "sakura", [
      "yui",
      "sakura",
      "nobody",
      "yui",
      "kenta",
      "daiki",
    ]);
    expect(picked.map((item) => item.id)).toEqual(["yui", "kenta"]);
  });
});

describe("togglePartner", () => {
  it("adds up to two and removes on a second press", () => {
    const one = togglePartner([], "kenta");
    const two = togglePartner(one, "yui");
    expect(two).toEqual(["kenta", "yui"]);
    expect(togglePartner(two, "daiki")).toEqual(["kenta", "yui"]);
    expect(togglePartner(two, "kenta")).toEqual(["yui"]);
  });
});

describe("maleBodyPairs", () => {
  it("pairs only residents who both have male bodies now", () => {
    const pairs = maleBodyPairs([sakura, kenta, daiki]);
    expect(pairs.map(([a, b]) => [a.id, b.id])).toEqual([["kenta", "daiki"]]);
  });

  it("ignores a former man who now has a female body", () => {
    const transformed = resident("kenta", "living", "female");
    expect(maleBodyPairs([transformed, daiki])).toEqual([]);
  });
});

describe("canContinueEvent", () => {
  it("allows today's events whose residents still live here", () => {
    const event = { day: 3, participants: ["sakura", "kenta"] };

    expect(canContinueEvent(event, 3, all)).toBe(true);
    // 前の日の出来事は続けられない
    expect(canContinueEvent(event, 4, all)).toBe(false);
    // 参加者が誰も残っていなければ続けられない
    expect(canContinueEvent({ day: 3, participants: ["gone"] }, 3, all)).toBe(
      false,
    );
  });
});
