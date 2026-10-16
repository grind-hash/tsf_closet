import { describe, expect, it } from "vitest";
import { insertPromptText } from "./insertPromptText";

describe("insertPromptText", () => {
  it("inserts into an empty field as is", () => {
    expect(insertPromptText("", "white dress", 0, 0)).toEqual({
      text: "white dress",
      caret: 11,
    });
  });

  it("adds a tag separator after a preceding tag", () => {
    expect(insertPromptText("1girl", "white dress", 5, 5)).toEqual({
      text: "1girl, white dress",
      caret: 18,
    });
  });

  it("adds only a space after a trailing comma", () => {
    expect(insertPromptText("1girl,", "smile", 6, 6).text).toBe("1girl, smile");
  });

  it("adds nothing after trailing whitespace", () => {
    expect(insertPromptText("1girl, ", "smile", 7, 7).text).toBe(
      "1girl, smile",
    );
  });

  it("separates from following text and places the caret after it", () => {
    const result = insertPromptText("1girl", "smile", 0, 0);
    expect(result.text).toBe("smile, 1girl");
    expect(result.caret).toBe(7);
  });

  it("does not add a trailing separator when the snippet already ends with one", () => {
    expect(insertPromptText("1girl", "smile, ", 0, 0).text).toBe(
      "smile, 1girl",
    );
  });

  it("replaces the selected range", () => {
    expect(
      insertPromptText("1girl, red dress, smile", "white dress", 7, 16),
    ).toEqual({ text: "1girl, white dress, smile", caret: 18 });
  });

  it("uses a space separator for prose fields", () => {
    expect(insertPromptText("こんにちは", "よろしく", 5, 5, " ").text).toBe(
      "こんにちは よろしく",
    );
  });

  it("clamps out-of-range selections", () => {
    expect(insertPromptText("ab", "c", 10, 12).text).toBe("ab, c");
  });
});
