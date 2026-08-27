import { describe, expect, it } from "vitest";
import {
  estimateAdventureTurnSeconds,
  isAdventureTurnTextOnly,
} from "./adventureTurnTimeEstimate";

// 手掛かり抽出のON/OFFは判定LLMがビジュアルLLMと並列のため見積もりに影響しない
describe("estimateAdventureTurnSeconds", () => {
  it("estimates a romance turn with both sprites on (non-composite) as 55s", () => {
    expect(
      estimateAdventureTurnSeconds({
        preset: "romance",
        enableCompositeScene: false,
        drawPortraitEveryTurn: true,
        drawPartnerEveryTurn: true,
      }),
    ).toBe(55);
  });

  it("adds the composite step on top of both sprites for romance", () => {
    expect(
      estimateAdventureTurnSeconds({
        preset: "romance",
        enableCompositeScene: true,
        drawPortraitEveryTurn: true,
        drawPartnerEveryTurn: true,
      }),
    ).toBe(75);
  });

  it("estimates a non-romance turn with portrait on (non-composite) as 40s", () => {
    expect(
      estimateAdventureTurnSeconds({
        preset: "infiltration",
        enableCompositeScene: false,
        drawPortraitEveryTurn: true,
        drawPartnerEveryTurn: true,
      }),
    ).toBe(40);
  });

  it("estimates a text-only turn (all image generation off) as 20s", () => {
    expect(
      estimateAdventureTurnSeconds({
        preset: "romance",
        enableCompositeScene: false,
        drawPortraitEveryTurn: false,
        drawPartnerEveryTurn: false,
      }),
    ).toBe(20);
  });

  it("keeps only the composite step when both sprite toggles are off", () => {
    expect(
      estimateAdventureTurnSeconds({
        preset: "romance",
        enableCompositeScene: true,
        drawPortraitEveryTurn: false,
        drawPartnerEveryTurn: false,
      }),
    ).toBe(40);
  });

  it("ignores the partner toggle outside the romance preset", () => {
    expect(
      estimateAdventureTurnSeconds({
        preset: "infiltration",
        enableCompositeScene: false,
        drawPortraitEveryTurn: false,
        drawPartnerEveryTurn: true,
      }),
    ).toBe(20);
  });
});

describe("isAdventureTurnTextOnly", () => {
  it("is true when every image toggle is off", () => {
    expect(
      isAdventureTurnTextOnly({
        preset: "romance",
        enableCompositeScene: false,
        drawPortraitEveryTurn: false,
        drawPartnerEveryTurn: false,
      }),
    ).toBe(true);
  });

  it("is true for a non-romance preset even when the partner toggle is on", () => {
    expect(
      isAdventureTurnTextOnly({
        preset: "infiltration",
        enableCompositeScene: false,
        drawPortraitEveryTurn: false,
        drawPartnerEveryTurn: true,
      }),
    ).toBe(true);
  });

  it("is false while the composite scene is still drawn", () => {
    expect(
      isAdventureTurnTextOnly({
        preset: "romance",
        enableCompositeScene: true,
        drawPortraitEveryTurn: false,
        drawPartnerEveryTurn: false,
      }),
    ).toBe(false);
  });

  it("is false while the romance partner sprite is still drawn", () => {
    expect(
      isAdventureTurnTextOnly({
        preset: "romance",
        enableCompositeScene: false,
        drawPortraitEveryTurn: false,
        drawPartnerEveryTurn: true,
      }),
    ).toBe(false);
  });
});

describe("companion mode", () => {
  it("counts only the partner sprite even with portrait and composite on", () => {
    expect(
      estimateAdventureTurnSeconds({
        preset: "romance",
        enableCompositeScene: true,
        drawPortraitEveryTurn: true,
        drawPartnerEveryTurn: true,
        companionMode: true,
      }),
    ).toBe(40);
  });

  it("is text-only exactly when the partner sprite is off", () => {
    expect(
      isAdventureTurnTextOnly({
        preset: "romance",
        enableCompositeScene: true,
        drawPortraitEveryTurn: true,
        drawPartnerEveryTurn: false,
        companionMode: true,
      }),
    ).toBe(true);
    expect(
      isAdventureTurnTextOnly({
        preset: "romance",
        enableCompositeScene: false,
        drawPortraitEveryTurn: false,
        drawPartnerEveryTurn: true,
        companionMode: true,
      }),
    ).toBe(false);
  });

  it("ignores the flag outside romance", () => {
    expect(
      estimateAdventureTurnSeconds({
        preset: "escape",
        enableCompositeScene: true,
        drawPortraitEveryTurn: true,
        drawPartnerEveryTurn: true,
        companionMode: true,
      }),
    ).toBe(60);
  });
});
