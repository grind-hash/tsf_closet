import { describe, expect, it } from "vitest";
import { estimateAdventureTurnSeconds } from "./adventureTurnTimeEstimate";

// 手掛かり抽出のON/OFFは判定LLMがビジュアルLLMと並列のため見積もりに影響しない
describe("estimateAdventureTurnSeconds", () => {
  it("estimates a romance turn with both sprites on (non-composite) as 55s", () => {
    expect(
      estimateAdventureTurnSeconds({
        preset: "romance",
        usePreciseReference: false,
        enableCompositeScene: false,
        drawPortraitEveryTurn: true,
        drawPartnerEveryTurn: true,
      }),
    ).toBe(55);
  });

  it("estimates a composite romance turn as 60s", () => {
    expect(
      estimateAdventureTurnSeconds({
        preset: "romance",
        usePreciseReference: false,
        enableCompositeScene: true,
        drawPortraitEveryTurn: true,
        drawPartnerEveryTurn: true,
      }),
    ).toBe(60);
  });

  it("estimates a non-romance turn with portrait on (non-composite) as 40s", () => {
    expect(
      estimateAdventureTurnSeconds({
        preset: "infiltration",
        usePreciseReference: false,
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
        usePreciseReference: false,
        enableCompositeScene: false,
        drawPortraitEveryTurn: false,
        drawPartnerEveryTurn: false,
      }),
    ).toBe(20);
  });

  it("forces sprite generation when precise reference is on", () => {
    expect(
      estimateAdventureTurnSeconds({
        preset: "romance",
        usePreciseReference: true,
        enableCompositeScene: false,
        drawPortraitEveryTurn: false,
        drawPartnerEveryTurn: false,
      }),
    ).toBe(55);
  });

  it("keeps the composite estimate even when sprite toggles are off", () => {
    expect(
      estimateAdventureTurnSeconds({
        preset: "romance",
        usePreciseReference: false,
        enableCompositeScene: true,
        drawPortraitEveryTurn: false,
        drawPartnerEveryTurn: false,
      }),
    ).toBe(60);
  });
});
