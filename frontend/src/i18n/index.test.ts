import { describe, expect, it } from "vitest";
import { en } from "./en";
import { ja } from "./ja";

function leafPaths(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null) {
    return [prefix];
  }
  return Object.entries(value).flatMap(([key, child]) =>
    leafPaths(child, prefix ? `${prefix}.${key}` : key),
  );
}

describe("i18n resources", () => {
  it("ja と en のキー構成が一致する", () => {
    expect(leafPaths(en).sort()).toEqual(leafPaths(ja).sort());
  });

  it("空文字の翻訳がない", () => {
    for (const lang of [ja, en]) {
      const empty = leafPaths(lang).filter((path) => {
        const text = path.split(".").reduce<unknown>((node, key) => {
          return typeof node === "object" && node !== null
            ? (node as Record<string, unknown>)[key]
            : undefined;
        }, lang);
        return typeof text !== "string" || text.length === 0;
      });
      expect(empty).toEqual([]);
    }
  });
});
