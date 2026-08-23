import { describe, expect, it } from "vitest";
import { V5_USAGE_WARN_SUPPRESSED_KEY } from "./novelaiImageModels";
import {
  DEFAULT_PROMPT_EXPANDER_IMAGE_MODEL,
  getMaxCharacterPrompts,
  getPromptExpanderImageModelLabel,
  MAX_CHARACTER_PROMPTS_V5,
  MAX_CHARACTER_PROMPTS_V45,
  NOVELAI_TEXT_MODEL_OPTIONS,
  PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS,
  PROMPT_EXPANDER_IMAGE_SIZES,
} from "./promptExpander";

describe("promptExpander constants", () => {
  it("lists the four NovelAI models in the expected order", () => {
    expect([...PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS]).toEqual([
      "nai-diffusion-5-full",
      "nai-diffusion-5-curated",
      "nai-diffusion-4-5-full",
      "nai-diffusion-4-5-curated",
    ]);
    expect(PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS).toContain(
      DEFAULT_PROMPT_EXPANDER_IMAGE_MODEL,
    );
  });

  it("returns the character prompt cap per model family", () => {
    expect(getMaxCharacterPrompts("nai-diffusion-5-full")).toBe(
      MAX_CHARACTER_PROMPTS_V5,
    );
    expect(getMaxCharacterPrompts("nai-diffusion-5-curated")).toBe(22);
    expect(getMaxCharacterPrompts("nai-diffusion-4-5-full")).toBe(
      MAX_CHARACTER_PROMPTS_V45,
    );
    expect(getMaxCharacterPrompts("nai-diffusion-4-5-curated")).toBe(6);
    // 未知のモデル名・空は V4.5 扱い（保守的な上限）
    expect(getMaxCharacterPrompts("unknown")).toBe(6);
    expect(getMaxCharacterPrompts(null)).toBe(6);
  });

  it("exposes sizes, text models and labels", () => {
    expect([...PROMPT_EXPANDER_IMAGE_SIZES]).toEqual([
      "portrait",
      "landscape",
      "square",
    ]);
    expect([...NOVELAI_TEXT_MODEL_OPTIONS]).toEqual(["glm-4-6", "xialong-v1"]);
    expect(getPromptExpanderImageModelLabel("nai-diffusion-5-full")).toBe(
      "NAI Diffusion V5 Full",
    );
    expect(getPromptExpanderImageModelLabel("custom")).toBe("custom");
  });

  it("shares the V5 usage warn suppression key with the game screens", () => {
    expect(V5_USAGE_WARN_SUPPRESSED_KEY).toBe("v5_usage_warn_suppressed");
  });
});
