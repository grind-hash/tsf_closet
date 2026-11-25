import { describe, expect, it } from "vitest";
import type { PreciseReference } from "../types";
import {
  clampReferenceStrength,
  isReferenceTypeSupported,
  referenceTypeUsesOutfit,
  resolveSendablePreciseReferences,
} from "./preciseReferences";

function reference(
  overrides: Partial<PreciseReference> = {},
): PreciseReference {
  return {
    id: "ref-1",
    imageData: "data:image/png;base64,AAAA",
    fileName: "ref.png",
    type: "character&style",
    includeOutfit: false,
    strength: 1,
    fidelity: 1,
    enabled: true,
    ...overrides,
  };
}

describe("preciseReferences", () => {
  it("uses the outfit flag only for character types", () => {
    expect(referenceTypeUsesOutfit("character&style")).toBe(true);
    expect(referenceTypeUsesOutfit("character")).toBe(true);
    expect(referenceTypeUsesOutfit("style")).toBe(false);
    expect(referenceTypeUsesOutfit("costume")).toBe(false);
  });

  it("allows costume references only on V5", () => {
    expect(isReferenceTypeSupported("costume", "v5")).toBe(true);
    expect(isReferenceTypeSupported("costume", "v4_5")).toBe(false);
    expect(isReferenceTypeSupported("style", "v4_5")).toBe(true);
  });

  it("clamps strength to the format range", () => {
    expect(clampReferenceStrength(3, "v4_5")).toBe(1);
    expect(clampReferenceStrength(3, "v5")).toBe(3);
    expect(clampReferenceStrength(9, "v5")).toBe(5);
    expect(clampReferenceStrength(-1, "v5")).toBe(0);
  });

  it("sends enabled V5 references as is", () => {
    const { references, skipReason } = resolveSendablePreciseReferences(
      [
        reference({ type: "character", includeOutfit: true, strength: 2.15 }),
        reference({ id: "ref-2", type: "costume" }),
        reference({ id: "ref-3", enabled: false }),
      ],
      { format: "v5", maskActive: false },
    );
    expect(skipReason).toBeNull();
    expect(references).toEqual([
      expect.objectContaining({
        type: "character",
        includeOutfit: true,
        strength: 2.15,
      }),
      expect.objectContaining({ type: "costume" }),
    ]);
  });

  it("drops costume and clamps strength on V4.5", () => {
    const { references } = resolveSendablePreciseReferences(
      [reference({ strength: 3 }), reference({ id: "ref-2", type: "costume" })],
      { format: "v4_5", maskActive: true },
    );
    expect(references).toEqual([
      expect.objectContaining({ type: "character&style", strength: 1 }),
    ]);
  });

  it("sends nothing on unsupported models and V5 inpainting", () => {
    expect(
      resolveSendablePreciseReferences([reference()], {
        format: null,
        maskActive: false,
      }),
    ).toEqual({ references: [], skipReason: "unsupportedModel" });
    expect(
      resolveSendablePreciseReferences([reference()], {
        format: "v5",
        maskActive: true,
      }),
    ).toEqual({ references: [], skipReason: "inpaintV5" });
    expect(
      resolveSendablePreciseReferences([], { format: null, maskActive: false }),
    ).toEqual({ references: [], skipReason: null });
  });
});
