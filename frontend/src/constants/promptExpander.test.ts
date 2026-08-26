import { describe, expect, it } from "vitest";
import { V5_USAGE_WARN_SUPPRESSED_KEY } from "./novelaiImageModels";
import {
  DEFAULT_PROMPT_EXPANDER_IMAGE_MODEL,
  DEFAULT_PROMPT_EXPANDER_REFERENCE_TYPE,
  getMaxCharacterPrompts,
  getPromptExpanderImageModelLabel,
  MAX_CHARACTER_PROMPTS_V5,
  MAX_CHARACTER_PROMPTS_V45,
  NOVELAI_TEXT_MODEL_OPTIONS,
  PROMPT_EXPANDER_ALPHA_OPTIONS,
  PROMPT_EXPANDER_ANLAS_PER_REFERENCE,
  PROMPT_EXPANDER_ANLAS_WARN_SUPPRESSED_KEY,
  PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS,
  PROMPT_EXPANDER_IMAGE_SIZES,
  PROMPT_EXPANDER_REFERENCE_TYPES,
  referenceTypeI18nKey,
  supportsPreciseReference,
  usesNativeTransparency,
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

  it("gates precise reference to V4.5 and native transparency to V5", () => {
    expect(supportsPreciseReference("nai-diffusion-4-5-full")).toBe(true);
    expect(supportsPreciseReference("nai-diffusion-4-5-curated")).toBe(true);
    expect(supportsPreciseReference("nai-diffusion-5-full")).toBe(false);
    expect(supportsPreciseReference("nai-diffusion-5-curated")).toBe(false);
    // 未知のモデル名・空は使えない扱い
    expect(supportsPreciseReference("unknown")).toBe(false);
    expect(supportsPreciseReference(null)).toBe(false);
    expect(usesNativeTransparency("nai-diffusion-5-curated")).toBe(true);
    expect(usesNativeTransparency("nai-diffusion-4-5-full")).toBe(false);
  });

  it("exposes reference types, cost and cut-out options mirrored from the backend", () => {
    expect([...PROMPT_EXPANDER_REFERENCE_TYPES]).toEqual([
      "character",
      "style",
      "character&style",
    ]);
    expect(PROMPT_EXPANDER_REFERENCE_TYPES).toContain(
      DEFAULT_PROMPT_EXPANDER_REFERENCE_TYPE,
    );
    // "&" は i18n のキーに使えないので写像する
    expect(referenceTypeI18nKey("character&style")).toBe("characterStyle");
    expect(referenceTypeI18nKey("style")).toBe("style");
    expect(PROMPT_EXPANDER_ANLAS_PER_REFERENCE).toBe(5);
    expect(PROMPT_EXPANDER_ANLAS_WARN_SUPPRESSED_KEY).toBe(
      "prompt_expander_anlas_warn_suppressed",
    );
    // 切り抜きの許容差は Adventure の立ち絵と同じ
    expect(PROMPT_EXPANDER_ALPHA_OPTIONS).toEqual({
      threshold: 12,
      featherRadius: 1.8,
    });
  });
});
