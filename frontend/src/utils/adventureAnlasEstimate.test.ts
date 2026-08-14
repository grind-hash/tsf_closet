import { describe, expect, it } from "vitest";
import { estimateAdventureAnlas } from "./adventureAnlasEstimate";

describe("estimateAdventureAnlas", () => {
  it("estimates a romance turn with composite scene as 10-15", () => {
    expect(
      estimateAdventureAnlas({
        kind: "turn",
        preset: "romance",
        enableCompositeScene: true,
      }),
    ).toEqual({ min: 10, max: 15 });
  });

  it("estimates a romance turn without composite scene as 10", () => {
    expect(
      estimateAdventureAnlas({
        kind: "turn",
        preset: "romance",
        enableCompositeScene: false,
      }),
    ).toEqual({ min: 10, max: 10 });
  });

  it("estimates a romance start with composite scene as 15-20", () => {
    expect(
      estimateAdventureAnlas({
        kind: "start",
        preset: "romance",
        enableCompositeScene: true,
      }),
    ).toEqual({ min: 15, max: 20 });
  });

  it("estimates a romance start without composite scene as 10", () => {
    expect(
      estimateAdventureAnlas({
        kind: "start",
        preset: "romance",
        enableCompositeScene: false,
      }),
    ).toEqual({ min: 10, max: 10 });
  });

  it("estimates a non-romance start with composite scene as 10", () => {
    expect(
      estimateAdventureAnlas({
        kind: "start",
        preset: "infiltration",
        enableCompositeScene: true,
      }),
    ).toEqual({ min: 10, max: 10 });
  });

  it("estimates a non-romance start without composite scene as 5", () => {
    expect(
      estimateAdventureAnlas({
        kind: "start",
        preset: "infiltration",
        enableCompositeScene: false,
      }),
    ).toEqual({ min: 5, max: 5 });
  });
});
