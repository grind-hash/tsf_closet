import { describe, expect, it } from "vitest";
import type { PromptExpanderEntry } from "../apis/promptExpander";
import { findStoryPickTarget } from "./promptExpanderStoryContext";

function makeEntry(
  id: string,
  createdAt: string,
  overrides: Partial<PromptExpanderEntry> = {},
): PromptExpanderEntry {
  return {
    id,
    session_id: "sess-1",
    kind: "generated",
    instruction: `${id} のネーム`,
    synopsis: `${id} のあらすじ`,
    positive_expand_mode: "japanese",
    negative_expand_mode: "off",
    character_mode: false,
    final_prompt: "1girl",
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
    image_url: `/prompt-expander/images/${id}`,
    nsfw: null,
    created_at: createdAt,
    ...overrides,
  };
}

// 一覧と同じく新しい順に並べる
const page1 = makeEntry("page-1", "2026-11-20T10:00:00");
const page2 = makeEntry("page-2", "2026-11-20T11:00:00");
const page3 = makeEntry("page-3", "2026-11-20T12:00:00");
const upload = makeEntry("upload-1", "2026-11-20T13:00:00", {
  kind: "uploaded",
  instruction: null,
  synopsis: null,
  final_prompt: "",
});
const entries = [upload, page3, page2, page1];

describe("findStoryPickTarget", () => {
  it("文の無いアップロードは飛ばし、まだ選んでいない一番新しいページへ移る", () => {
    expect(findStoryPickTarget(entries, [], 5)?.id).toBe("page-3");
    expect(findStoryPickTarget(entries, ["page-3"], 5)?.id).toBe("page-2");
  });

  it("並び順に頼らず生成日時で一番新しいページを選ぶ", () => {
    expect(findStoryPickTarget([page1, page3, page2], [], 5)?.id).toBe(
      "page-3",
    );
  });

  it("すべて選んでいるときは選択中の一番新しいページへ移る", () => {
    expect(
      findStoryPickTarget(entries, ["page-1", "page-2", "page-3"], 5)?.id,
    ).toBe("page-3");
  });

  it("上限まで選んでいるときは「外す」が押せる選択中のページへ移る", () => {
    expect(findStoryPickTarget(entries, ["page-1", "page-2"], 2)?.id).toBe(
      "page-2",
    );
  });

  it("選べるページが無ければ null", () => {
    expect(findStoryPickTarget([upload], [], 5)).toBeNull();
    expect(findStoryPickTarget([], [], 5)).toBeNull();
  });
});
