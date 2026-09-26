import { describe, expect, it } from "vitest";

import { shouldShowCost } from "./system";

describe("shouldShowCost", () => {
  it("サーバーが cost_tracking を返すならそれに従う", () => {
    expect(
      shouldShowCost({
        image_provider: "novelai",
        image_description_provider: "novelai",
        feeling_provider: "novelai",
        cost_tracking: true,
      }),
    ).toBe(true);
  });

  it("生成プロバイダーが openrouter でも cost_tracking が false なら出さない", () => {
    expect(
      shouldShowCost({
        image_provider: "openrouter",
        cost_tracking: false,
      }),
    ).toBe(false);
  });

  it("cost_tracking を返さない旧サーバーではプロバイダー名から推定する", () => {
    expect(
      shouldShowCost({
        image_provider: "novelai",
        image_description_provider: "selfhost",
        feeling_provider: "openrouter",
      }),
    ).toBe(true);
    expect(
      shouldShowCost({
        image_provider: "novelai",
        image_description_provider: "selfhost",
        feeling_provider: "novelai",
      }),
    ).toBe(false);
  });

  it("空の応答では出さない", () => {
    expect(shouldShowCost({})).toBe(false);
  });
});
