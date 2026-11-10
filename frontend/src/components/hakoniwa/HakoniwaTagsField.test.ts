import { describe, expect, it } from "vitest";
import { editedTags } from "./HakoniwaTagsField";

describe("editedTags", () => {
  it("sends nothing when the tags were not changed", () => {
    expect(editedTags("1girl, maid outfit ", "1girl, maid outfit", false)).toBe(
      null,
    );
  });

  it("sends the hand-edited tags, or an empty string to go back to auto", () => {
    expect(editedTags("1girl, cat ears", "1girl", false)).toBe(
      "1girl, cat ears",
    );
    expect(editedTags("  ", "1girl", false)).toBe("");
  });

  it("sends no tags while remaking them from the description", () => {
    expect(editedTags("1girl, cat ears", "1girl", true)).toBe(null);
  });
});
