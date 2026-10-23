import { describe, expect, it } from "vitest";
import type {
  FavoritePrompt,
  FavoritePromptCategory,
} from "../apis/favoritePrompts";
import { moveFavoritePrompt } from "./favoritePromptOrder";

function prompt(id: string, categoryId: string | null): FavoritePrompt {
  return {
    id,
    category_id: categoryId,
    label: id,
    content: id,
    color: "#6B7280",
    sort_order: 0,
    created_at: "",
    updated_at: "",
  };
}

function category(id: string): FavoritePromptCategory {
  return {
    id,
    label: id,
    color: "#6B7280",
    sort_order: 0,
    created_at: "",
    updated_at: "",
  };
}

const categories = [category("outfit"), category("face")];
// 表示順: 未分類 [a, b] → outfit [c, d] → face []
const prompts = [
  prompt("c", "outfit"),
  prompt("a", null),
  prompt("d", "outfit"),
  prompt("b", null),
];

function order(result: ReturnType<typeof moveFavoritePrompt>) {
  return result?.map((p) => `${p.category_id ?? "-"}:${p.id}`);
}

describe("moveFavoritePrompt", () => {
  it("reorders within the same group", () => {
    const result = moveFavoritePrompt(prompts, categories, "b", {
      categoryId: null,
      beforeId: "a",
    });
    expect(order(result)).toEqual(["-:b", "-:a", "outfit:c", "outfit:d"]);
  });

  it("moves into another category before a chip or to its end", () => {
    expect(
      order(
        moveFavoritePrompt(prompts, categories, "a", {
          categoryId: "outfit",
          beforeId: "d",
        }),
      ),
    ).toEqual(["-:b", "outfit:c", "outfit:a", "outfit:d"]);

    expect(
      order(
        moveFavoritePrompt(prompts, categories, "c", {
          categoryId: "face",
          beforeId: null,
        }),
      ),
    ).toEqual(["-:a", "-:b", "outfit:d", "face:c"]);
  });

  it("returns null when nothing changes", () => {
    expect(
      moveFavoritePrompt(prompts, categories, "a", {
        categoryId: null,
        beforeId: "b",
      }),
    ).toBeNull();
    expect(
      moveFavoritePrompt(prompts, categories, "d", {
        categoryId: "outfit",
        beforeId: null,
      }),
    ).toBeNull();
    expect(
      moveFavoritePrompt(prompts, categories, "a", {
        categoryId: "missing",
        beforeId: null,
      }),
    ).toBeNull();
  });

  it("treats prompts in unknown categories as uncategorized", () => {
    const result = moveFavoritePrompt(
      [prompt("x", "deleted"), prompt("y", null)],
      categories,
      "y",
      { categoryId: null, beforeId: "x" },
    );
    expect(order(result)).toEqual(["-:y", "-:x"]);
  });
});
