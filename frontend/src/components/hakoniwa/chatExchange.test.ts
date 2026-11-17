import { describe, expect, it } from "vitest";
import type { HakoniwaChatEntry } from "../../apis/hakoniwa";
import { latestExchange } from "./chatExchange";

const player = (text: string): HakoniwaChatEntry => ({ role: "player", text });
const resident = (text: string): HakoniwaChatEntry => ({
  role: "resident",
  text,
});

describe("latestExchange", () => {
  it("pairs the latest reply with the player's line before it", () => {
    const result = latestExchange([
      player("おはよう"),
      resident("おはよう！"),
      player("今日は晴れだね"),
      resident("ほんとだね"),
    ]);
    expect(result.latest?.text).toBe("ほんとだね");
    expect(result.lastPlayerLine).toBe("今日は晴れだね");
  });

  it("skips the system notice after a transformation", () => {
    const result = latestExchange([
      player("メイド服に着替えて"),
      { role: "system", text: "変身しました", kind: "alteration" },
      resident("どうかな？"),
    ]);
    expect(result.latest?.text).toBe("どうかな？");
    expect(result.lastPlayerLine).toBe("メイド服に着替えて");
  });

  it("ignores a trailing player line that has no reply yet", () => {
    const result = latestExchange([
      player("やあ"),
      resident("こんにちは"),
      player("返事待ち"),
    ]);
    expect(result.latest?.text).toBe("こんにちは");
    expect(result.lastPlayerLine).toBe("やあ");
  });

  it("handles an empty history", () => {
    expect(latestExchange([])).toEqual({
      latest: undefined,
      lastPlayerLine: undefined,
    });
  });
});
