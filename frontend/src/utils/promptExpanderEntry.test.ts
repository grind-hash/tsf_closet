import { describe, expect, it } from "vitest";
import type { PromptExpanderEntry } from "../apis/promptExpander";
import { isEntryFromScript } from "./promptExpanderEntry";

const base: PromptExpanderEntry = {
  id: "entry-1",
  session_id: "sess-1",
  kind: "generated",
  instruction: "①鏡を見る「え…？」",
  positive_expand_mode: "tags",
  negative_expand_mode: "off",
  character_mode: false,
  final_prompt: "1girl, comic",
  final_negative_prompt: "",
  character_prompts: [],
  image_model: null,
  text_model: null,
  seed: null,
  i2i_strength: null,
  i2i_noise: null,
  image_size: null,
  manga_mode: true,
  manga_panel_count: null,
  source_kind: "none",
  source_history_id: null,
  source_entry_id: null,
  transparent_background: false,
  references: [],
  inpaint: false,
  mask_url: null,
  image_url: "/prompt-expander/images/entry-1",
  nsfw: null,
  created_at: "2026-11-28T10:00:00",
};

describe("isEntryFromScript", () => {
  it("記録された欄に従う（あらすじが空の手書きネームもネームとみなす）", () => {
    expect(isEntryFromScript({ ...base, instruction_source: "script" })).toBe(
      true,
    );
    expect(
      isEntryFromScript({
        ...base,
        instruction_source: "instruction",
        synopsis: "あらすじ",
      }),
    ).toBe(false);
  });

  it("記録前の古いエントリはあらすじの有無で見分ける", () => {
    expect(isEntryFromScript({ ...base, synopsis: "あらすじ" })).toBe(true);
    expect(isEntryFromScript({ ...base, synopsis: "  " })).toBe(false);
    expect(isEntryFromScript({ ...base, synopsis: null })).toBe(false);
  });
});
