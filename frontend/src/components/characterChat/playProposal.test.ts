// @vitest-environment node
import { describe, expect, it } from "vitest";
import type { CharacterChatMessageMeta } from "../../apis/characterChat";
import { toPlayProposal } from "./playProposal";

const VALID = {
  kind: "play",
  title: " 放課後の着せ替え ",
  reason: " 最近は制服が多いので、秋物で趣向を変えてみます。 ",
  character: { source: "template", id: "sakura", name: " サクラ " },
  self_mode: false,
  first_instruction: {
    instruction_type: "dress_up",
    text: " 秋物のカーディガンとロングスカートに着替える ",
  },
};

/** サーバーから届く任意の形を meta に載せる */
function metaWith(proposal: unknown): CharacterChatMessageMeta {
  return { play_proposal: proposal } as CharacterChatMessageMeta;
}

describe("toPlayProposal", () => {
  it("accepts a valid play proposal and trims the texts", () => {
    expect(toPlayProposal(metaWith(VALID))).toEqual({
      kind: "play",
      title: "放課後の着せ替え",
      reason: "最近は制服が多いので、秋物で趣向を変えてみます。",
      character: { source: "template", id: "sakura", name: "サクラ" },
      self_mode: false,
      first_instruction: {
        instruction_type: "dress_up",
        text: "秋物のカーディガンとロングスカートに着替える",
      },
    });
  });

  it("accepts a custom character in self mode with an empty reason", () => {
    const proposal = toPlayProposal(
      metaWith({
        ...VALID,
        reason: "",
        character: { source: "custom", id: "c-1", name: "サクラ" },
        self_mode: true,
        first_instruction: { instruction_type: "conversation", text: "話す" },
      }),
    );
    expect(proposal?.character).toEqual({
      source: "custom",
      id: "c-1",
      name: "サクラ",
    });
    expect(proposal?.self_mode).toBe(true);
    expect(proposal?.reason).toBe("");
    expect(proposal?.first_instruction.instruction_type).toBe("conversation");
  });

  it("returns null when there is no proposal", () => {
    expect(toPlayProposal(undefined)).toBeNull();
    expect(toPlayProposal(null)).toBeNull();
    expect(toPlayProposal({})).toBeNull();
    expect(toPlayProposal(metaWith(null))).toBeNull();
  });

  it("returns null for unknown or missing kinds", () => {
    expect(
      toPlayProposal(metaWith({ ...VALID, kind: "adventure" })),
    ).toBeNull();
    const { kind: _kind, ...withoutKind } = VALID;
    expect(toPlayProposal(metaWith(withoutKind))).toBeNull();
  });

  it.each([
    ["a string", "play"],
    ["an array", [VALID]],
    ["an empty title", { ...VALID, title: "  " }],
    ["a non-string reason", { ...VALID, reason: 1 }],
    ["a non-boolean self_mode", { ...VALID, self_mode: "true" }],
    ["a missing character", { ...VALID, character: null }],
    [
      "an unknown character source",
      { ...VALID, character: { ...VALID.character, source: "preset" } },
    ],
    [
      "an empty character id",
      { ...VALID, character: { ...VALID.character, id: "" } },
    ],
    [
      "a missing character name",
      { ...VALID, character: { source: "template", id: "sakura" } },
    ],
    ["a missing first instruction", { ...VALID, first_instruction: undefined }],
    [
      "the image_only instruction type",
      {
        ...VALID,
        first_instruction: { instruction_type: "image_only", text: "描く" },
      },
    ],
    [
      "an unknown instruction type",
      { ...VALID, first_instruction: { instruction_type: "bogus", text: "x" } },
    ],
    [
      "an empty instruction text",
      {
        ...VALID,
        first_instruction: { instruction_type: "dress_up", text: " " },
      },
    ],
  ])("returns null for %s", (_label, proposal) => {
    expect(toPlayProposal(metaWith(proposal))).toBeNull();
  });
});
