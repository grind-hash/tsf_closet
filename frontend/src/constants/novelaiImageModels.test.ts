import { describe, expect, it } from "vitest";
import {
  DEFAULT_NSFW_IMAGE_MODEL,
  DEFAULT_SFW_IMAGE_MODEL,
  isEconomyImageModel,
  isV5ImageModel,
  NSFW_IMAGE_MODEL_OPTIONS,
  preciseReferenceFormat,
  resolveEffectiveNovelaiImageModel,
  SFW_IMAGE_MODEL_OPTIONS,
} from "./novelaiImageModels";

describe("novelaiImageModels", () => {
  it("maps each model to its precise reference format", () => {
    expect(preciseReferenceFormat("nai-diffusion-5-full")).toBe("v5");
    expect(preciseReferenceFormat("nai-diffusion-5-curated")).toBe("v5");
    expect(preciseReferenceFormat("nai-diffusion-5-full-medium")).toBeNull();
    expect(preciseReferenceFormat("nai-diffusion-4-5-full")).toBe("v4_5");
    expect(preciseReferenceFormat("nai-diffusion-4-5-curated")).toBe("v4_5");
    // 未知名・空はバックエンドと同じく v4.5 相当
    expect(preciseReferenceFormat("custom-model")).toBe("v4_5");
    expect(preciseReferenceFormat("")).toBe("v4_5");
    expect(preciseReferenceFormat(null)).toBe("v4_5");
  });

  it("resolves the effective model from the NSFW setting", () => {
    const models = {
      novelaiImageModel: "nai-diffusion-5-full",
      novelaiCuratedImageModel: "nai-diffusion-4-5-curated",
    };
    expect(
      resolveEffectiveNovelaiImageModel({ ...models, nsfwMode: true }),
    ).toBe("nai-diffusion-5-full");
    expect(
      resolveEffectiveNovelaiImageModel({ ...models, nsfwMode: false }),
    ).toBe("nai-diffusion-4-5-curated");
  });

  it("keeps the V4.5 models as defaults", () => {
    expect(DEFAULT_NSFW_IMAGE_MODEL).toBe("nai-diffusion-4-5-full");
    expect(DEFAULT_SFW_IMAGE_MODEL).toBe("nai-diffusion-4-5-curated");
    expect(NSFW_IMAGE_MODEL_OPTIONS[0]).toBe(DEFAULT_NSFW_IMAGE_MODEL);
    expect(SFW_IMAGE_MODEL_OPTIONS[0]).toBe(DEFAULT_SFW_IMAGE_MODEL);
  });

  it("detects V5 models only", () => {
    expect(isV5ImageModel("nai-diffusion-5-full")).toBe(true);
    expect(isV5ImageModel("nai-diffusion-5-curated")).toBe(true);
    expect(isV5ImageModel("nai-diffusion-5-full-medium")).toBe(true);
    expect(isV5ImageModel("nai-diffusion-4-5-full")).toBe(false);
    expect(isV5ImageModel("nai-diffusion-4-5-curated")).toBe(false);
    expect(isV5ImageModel("")).toBe(false);
    expect(isV5ImageModel(null)).toBe(false);
    expect(isV5ImageModel(undefined)).toBe(false);
  });

  it("detects the economy (Medium effort) model only", () => {
    expect(NSFW_IMAGE_MODEL_OPTIONS).toContain("nai-diffusion-5-full-medium");
    expect(SFW_IMAGE_MODEL_OPTIONS).not.toContain(
      "nai-diffusion-5-full-medium",
    );
    expect(isEconomyImageModel("nai-diffusion-5-full-medium")).toBe(true);
    expect(isEconomyImageModel("nai-diffusion-5-full")).toBe(false);
    expect(isEconomyImageModel("nai-diffusion-4-5-full")).toBe(false);
    expect(isEconomyImageModel("")).toBe(false);
    expect(isEconomyImageModel(null)).toBe(false);
    expect(isEconomyImageModel(undefined)).toBe(false);
  });
});
