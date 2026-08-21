import { describe, expect, it } from "vitest";
import {
  DEFAULT_NSFW_IMAGE_MODEL,
  DEFAULT_SFW_IMAGE_MODEL,
  isV5ImageModel,
  NSFW_IMAGE_MODEL_OPTIONS,
  SFW_IMAGE_MODEL_OPTIONS,
} from "./novelaiImageModels";

describe("novelaiImageModels", () => {
  it("keeps the V4.5 models as defaults", () => {
    expect(DEFAULT_NSFW_IMAGE_MODEL).toBe("nai-diffusion-4-5-full");
    expect(DEFAULT_SFW_IMAGE_MODEL).toBe("nai-diffusion-4-5-curated");
    expect(NSFW_IMAGE_MODEL_OPTIONS[0]).toBe(DEFAULT_NSFW_IMAGE_MODEL);
    expect(SFW_IMAGE_MODEL_OPTIONS[0]).toBe(DEFAULT_SFW_IMAGE_MODEL);
  });

  it("detects V5 models only", () => {
    expect(isV5ImageModel("nai-diffusion-5-full")).toBe(true);
    expect(isV5ImageModel("nai-diffusion-5-curated")).toBe(true);
    expect(isV5ImageModel("nai-diffusion-4-5-full")).toBe(false);
    expect(isV5ImageModel("nai-diffusion-4-5-curated")).toBe(false);
    expect(isV5ImageModel("")).toBe(false);
    expect(isV5ImageModel(null)).toBe(false);
    expect(isV5ImageModel(undefined)).toBe(false);
  });
});
