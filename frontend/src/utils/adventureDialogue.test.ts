import { describe, expect, it } from "vitest";
import {
  ensureSentenceEnd,
  joinForSpeech,
  parseDialogueSegments,
  partnerLines,
  splitForSpeech,
  stripStageDirections,
  stripTalkHeader,
} from "./adventureDialogue";

describe("stripTalkHeader", () => {
  it("strips the canonical header line", () => {
    expect(stripTalkHeader("[expression=happy gesture=nod]\nやっほー")).toBe(
      "やっほー",
    );
  });

  it("strips malformed shorthand headers the LLM sometimes emits", () => {
    expect(stripTalkHeader("[surprised=tilt_head] えっと…")).toBe("えっと…");
    expect(stripTalkHeader("[happy, wave_hand]やっほー")).toBe("やっほー");
    expect(stripTalkHeader("[gesture: nod]うん")).toBe("うん");
  });

  it("keeps brackets that are not headers", () => {
    expect(stripTalkHeader("[こんにちは] やっほー")).toBe(
      "[こんにちは] やっほー",
    );
    expect(stripTalkHeader("やっほー")).toBe("やっほー");
  });
});

describe("parseDialogueSegments", () => {
  it("splits name-prefixed lines into dialogue and merges narration", () => {
    const text = [
      "夕暮れの教室。",
      "窓際に美咲が立っていた。",
      "美咲「やっほー、まだ残ってたんだ」",
      "主人公「うん、少しね」",
      "",
      "彼女は笑った。",
    ].join("\n");
    expect(parseDialogueSegments(text, ["美咲", "主人公"])).toEqual([
      { kind: "narration", text: "夕暮れの教室。\n窓際に美咲が立っていた。" },
      { kind: "dialogue", speaker: "美咲", text: "やっほー、まだ残ってたんだ" },
      { kind: "dialogue", speaker: "主人公", text: "うん、少しね" },
      { kind: "narration", text: "彼女は笑った。" },
    ]);
  });

  it("accepts colon variants and unclosed streaming lines", () => {
    expect(parseDialogueSegments("美咲：「そうだね」", ["美咲"])).toEqual([
      { kind: "dialogue", speaker: "美咲", text: "そうだね" },
    ]);
    expect(parseDialogueSegments("Misaki: Sure thing.", ["Misaki"])).toEqual([
      { kind: "dialogue", speaker: "Misaki", text: "Sure thing." },
    ]);
    // ストリーミング途中で閉じ括弧が無い行も話者付きとして扱う
    expect(parseDialogueSegments("美咲「まだ途中", ["美咲"])).toEqual([
      { kind: "dialogue", speaker: "美咲", text: "まだ途中" },
    ]);
  });

  it("does not treat prose that merely starts with the name as dialogue", () => {
    expect(parseDialogueSegments("美咲は笑った。", ["美咲"])).toEqual([
      { kind: "narration", text: "美咲は笑った。" },
    ]);
    expect(parseDialogueSegments("地の文だけ", [])).toEqual([
      { kind: "narration", text: "地の文だけ" },
    ]);
  });
});

describe("partnerLines / joinForSpeech / stripStageDirections", () => {
  it("extracts only the partner's lines in order and joins them for speech", () => {
    const text = "美咲「おはよう」\n主人公「おはよう」\n美咲「今日も暑いね！」";
    const lines = partnerLines(text, "美咲");
    expect(lines).toEqual(["おはよう", "今日も暑いね！"]);
    expect(joinForSpeech(lines)).toBe("おはよう。今日も暑いね！");
    expect(partnerLines(text, "")).toEqual([]);
  });

  it("strips stage directions and corner brackets", () => {
    expect(
      stripStageDirections(
        "（笑って）そうだね、「好き」って言った (small nod)",
      ),
    ).toBe("そうだね、好きって言った");
  });
});

describe("ensureSentenceEnd", () => {
  it("appends a period only when the line lacks a sentence-ending mark", () => {
    expect(ensureSentenceEnd("おはよう")).toBe("おはよう。");
    expect(ensureSentenceEnd("暑いね！")).toBe("暑いね！");
    expect(ensureSentenceEnd("そうかな…")).toBe("そうかな…");
    expect(ensureSentenceEnd("  ")).toBe("");
  });
});

describe("splitForSpeech", () => {
  it("splits text into sentence segments", () => {
    expect(
      splitForSpeech("今日は良い天気ですね。散歩に行きませんか？"),
    ).toEqual(["今日は良い天気ですね。", "散歩に行きませんか？"]);
  });

  it("merges short fragments with the following sentence", () => {
    expect(
      splitForSpeech(
        "え？そうなの？知らなかったよ、全然気づかなかった。明日一緒に見に行こうよ。",
      ),
    ).toEqual([
      "え？そうなの？知らなかったよ、全然気づかなかった。",
      "明日一緒に見に行こうよ。",
    ]);
  });

  it("merges a short trailing fragment into the previous segment", () => {
    expect(splitForSpeech("知らなかった、教えてくれる？ね？")).toEqual([
      "知らなかった、教えてくれる？ね？",
    ]);
  });

  it("re-splits an overlong sentence at pause marks", () => {
    const long = `${"あ".repeat(100)}、${"い".repeat(100)}、${"う".repeat(20)}。`;
    expect(splitForSpeech(long)).toEqual([
      `${"あ".repeat(100)}、`,
      `${"い".repeat(100)}、`,
      `${"う".repeat(20)}。`,
    ]);
  });

  it("keeps an overlong sentence without pause marks as one segment", () => {
    const long = `${"あ".repeat(150)}。`;
    expect(splitForSpeech(long)).toEqual([long]);
  });

  it("returns an empty list for blank input", () => {
    expect(splitForSpeech("")).toEqual([]);
    expect(splitForSpeech("  \n ")).toEqual([]);
  });
});
