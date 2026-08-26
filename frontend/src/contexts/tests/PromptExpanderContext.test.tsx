import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PromptExpanderEntry } from "../../apis/promptExpander";
import { V5_USAGE_WARN_SUPPRESSED_KEY } from "../../constants/novelaiImageModels";
import { NotificationProvider } from "../NotificationContext";
import {
  PromptExpanderProvider,
  usePromptExpander,
} from "../PromptExpanderContext";
import { SettingsProvider } from "../SettingsContext";

// ----------------------------------------------------------------
// fetch モック
// ----------------------------------------------------------------

interface MockState {
  imageModel: string;
  anlasUsagePercent: number | null;
  /** /expand をこのエラーコードで失敗させる（null なら成功） */
  expandErrorCode: string | null;
  /** 設定 GET が返す restore_seed */
  restoreSeed: boolean;
}

const mockState: MockState = {
  imageModel: "nai-diffusion-4-5-full",
  anlasUsagePercent: null,
  expandErrorCode: null,
  restoreSeed: false,
};

const calls: Array<{ url: string; init?: RequestInit }> = [];

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "OK",
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function settingsPayload() {
  return {
    settings: {
      text_model: "glm-4-6",
      image_model: mockState.imageModel,
      image_size: "portrait",
      i2i_strength: 0.5,
      i2i_noise: 0.1,
      seed: null,
      restore_seed: mockState.restoreSeed,
      memory_text: "",
      use_memory: false,
      confirm_before_generate: true,
      inherit_source_prompts: true,
      manga_mode: false,
      manga_panel_count: 0,
      manga_layout: "auto",
      manga_dialogue: true,
      manga_text_language: "auto",
      manga_sound_effects: true,
      manga_reading_direction: "rtl",
      manga_narration: false,
    },
    text_model_options: [
      { id: "glm-4-6", label: "GLM 4.6" },
      { id: "xialong-v1", label: "Xialong" },
    ],
    image_model_options: [
      "nai-diffusion-5-full",
      "nai-diffusion-5-curated",
      "nai-diffusion-4-5-full",
      "nai-diffusion-4-5-curated",
    ],
    max_character_prompts: {
      "nai-diffusion-5-full": 22,
      "nai-diffusion-5-curated": 22,
      "nai-diffusion-4-5-full": 6,
      "nai-diffusion-4-5-curated": 6,
    },
    image_sizes: ["portrait", "landscape", "square"],
    novelai_configured: true,
  };
}

function anlasPayload() {
  return {
    fixed_anlas: 100,
    purchased_anlas: 0,
    total_anlas: 100,
    usage:
      mockState.anlasUsagePercent === null
        ? null
        : {
            percent: mockState.anlasUsagePercent,
            is_negative: mockState.anlasUsagePercent < 0,
            time_until_next_percent: 0,
          },
  };
}

const SESSION = {
  id: "sess-1",
  title: "Test session",
  entry_count: 1,
  thumbnail_url: "/prompt-expander/images/entry-old",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const OLD_ENTRY: PromptExpanderEntry = {
  id: "entry-old",
  session_id: "sess-1",
  kind: "generated",
  instruction: "old instruction",
  positive_expand_mode: "tags",
  negative_expand_mode: "off",
  character_mode: true,
  final_prompt: "1girl, old prompt",
  final_negative_prompt: "lowres",
  character_prompts: ["girl A", "girl B"],
  image_model: "nai-diffusion-5-full",
  text_model: "glm-4-6",
  seed: 12345,
  i2i_strength: 0.7,
  i2i_noise: 0.2,
  image_size: "landscape",
  manga_mode: false,
  manga_panel_count: null,
  source_kind: "none",
  source_history_id: null,
  source_entry_id: null,
  image_url: "/prompt-expander/images/entry-old",
  nsfw: false,
  created_at: "2026-01-01T00:00:00Z",
};

function makeGeneratedEntry(
  body: Record<string, unknown>,
): PromptExpanderEntry {
  return {
    ...OLD_ENTRY,
    id: "entry-new",
    instruction: (body.instruction as string | null) ?? null,
    final_prompt: String(body.prompt),
    final_negative_prompt: String(body.negative_prompt ?? ""),
    character_prompts: (body.character_prompts as string[]) ?? [],
    image_model: String(body.image_model),
    image_url: "/prompt-expander/images/entry-new",
    created_at: "2026-01-02T00:00:00Z",
  };
}

const fetchMock = vi.fn(
  async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === "string" ? input : input.toString();
    calls.push({ url, init });
    const method = init?.method ?? "GET";

    if (url === "/api/prompt-expander/settings") {
      const payload = settingsPayload();
      if (method === "PUT") {
        // 部分更新をそのまま反映して返す（バックエンドの挙動を模倣）
        const patch = JSON.parse(String(init?.body));
        return jsonResponse({
          ...payload,
          settings: { ...payload.settings, ...patch },
        });
      }
      return jsonResponse(payload);
    }
    if (url === "/api/game/anlas") {
      return jsonResponse(anlasPayload());
    }
    if (url === "/api/prompt-expander/sessions/sess-1" && method === "GET") {
      return jsonResponse({ session: SESSION, entries: [OLD_ENTRY] });
    }
    if (url === "/api/prompt-expander/expand" && method === "POST") {
      if (mockState.expandErrorCode) {
        return jsonResponse(
          {
            detail: {
              code: mockState.expandErrorCode,
              message: `failed: ${mockState.expandErrorCode}`,
            },
          },
          400,
        );
      }
      const body = JSON.parse(String(init?.body));
      return jsonResponse({
        positive_prompt: body.expand_positive
          ? `expanded: ${body.instruction}`
          : null,
        character_prompts:
          body.expand_positive && body.character_mode
            ? ["expanded char 1", "expanded char 2"]
            : null,
        negative_prompt: body.expand_negative
          ? `expanded negative: ${body.negative_instruction}`
          : null,
        text_model: "glm-4-6",
      });
    }
    if (url === "/api/prompt-expander/manga-script" && method === "POST") {
      const body = JSON.parse(String(init?.body));
      return jsonResponse({
        script: `①${body.instruction}「え…？」\n②戸惑う『どうして…』`,
        text_model: "glm-4-6",
      });
    }
    if (
      url === "/api/prompt-expander/suggest-characters" &&
      method === "POST"
    ) {
      return jsonResponse({
        suggestions: [{ title: "銀髪", prompt: "1girl, silver hair" }],
        text_model: "glm-4-6",
      });
    }
    if (
      url === "/api/prompt-expander/sessions/sess-1/generate" &&
      method === "POST"
    ) {
      const body = JSON.parse(String(init?.body));
      return jsonResponse({
        entry: makeGeneratedEntry(body),
        anlas: anlasPayload(),
      });
    }
    return { ok: false, status: 404, json: async () => ({}) } as Response;
  },
);

function findCalls(urlPart: string, method?: string) {
  return calls.filter(
    (c) =>
      c.url.includes(urlPart) &&
      (method ? (c.init?.method ?? "GET") === method : true),
  );
}

function lastBody(urlPart: string, method: string): Record<string, unknown> {
  const list = findCalls(urlPart, method);
  return JSON.parse(String(list[list.length - 1].init?.body));
}

// ----------------------------------------------------------------
// プローブ
// ----------------------------------------------------------------

function Probe() {
  const ctx = usePromptExpander();
  return (
    <>
      <div data-testid="session">{ctx.activeSession?.id ?? "none"}</div>
      <div data-testid="settings-loaded">
        {ctx.settingsLoaded ? "yes" : "no"}
      </div>
      <div data-testid="image-model">{ctx.settings.image_model}</div>
      <div data-testid="entries">{ctx.entries.map((e) => e.id).join(",")}</div>
      <div data-testid="pending-expansion">
        {ctx.pendingExpansion ? JSON.stringify(ctx.pendingExpansion) : "none"}
      </div>
      <div data-testid="pending-usage">
        {ctx.pendingUsageWarn ? "yes" : "no"}
      </div>
      <div data-testid="positive">{ctx.positiveText}</div>
      <div data-testid="negative">{ctx.negativeText}</div>
      <div data-testid="positive-origin">
        {ctx.positiveOrigin ? JSON.stringify(ctx.positiveOrigin) : "none"}
      </div>
      <div data-testid="negative-origin">
        {ctx.negativeOrigin ? JSON.stringify(ctx.negativeOrigin) : "none"}
      </div>
      <div data-testid="expansion-error">
        {ctx.expansionError ? JSON.stringify(ctx.expansionError) : "none"}
      </div>
      <div data-testid="expanding">{ctx.expandingTarget ?? "none"}</div>
      <div data-testid="drafting">{ctx.draftingScript ? "yes" : "no"}</div>
      <div data-testid="draft-backup">
        {ctx.scriptDraftBackup ? ctx.scriptDraftBackup.source : "none"}
      </div>
      <div data-testid="character-mode">{ctx.characterMode ? "on" : "off"}</div>
      <div data-testid="manga-active">{ctx.mangaActive ? "on" : "off"}</div>
      <div data-testid="slots">{ctx.characterSlots.join("|")}</div>
      <div data-testid="anlas">{ctx.anlas ? ctx.anlas.totalAnlas : "none"}</div>
      <div data-testid="error">{ctx.error ?? ""}</div>
      <div data-testid="disabled-reason">
        {ctx.generateDisabledReason ?? "none"}
      </div>
      <button type="button" onClick={() => void ctx.openSession("sess-1")}>
        open
      </button>
      <button type="button" onClick={() => ctx.setPositiveText("a cat girl")}>
        set-positive
      </button>
      <button type="button" onClick={() => ctx.setPositiveText("a dog girl")}>
        set-positive-2
      </button>
      <button type="button" onClick={() => ctx.setPositiveText("")}>
        clear-positive
      </button>
      <button type="button" onClick={() => ctx.setNegativeText("blurry")}>
        set-negative
      </button>
      <button type="button" onClick={() => ctx.setPositiveMode("japanese")}>
        positive-japanese
      </button>
      <button type="button" onClick={() => ctx.setCharacterMode(true)}>
        character-on
      </button>
      <button
        type="button"
        onClick={() =>
          void ctx.updateSettings({
            manga_mode: true,
            manga_panel_count: 3,
            manga_layout: "vertical",
            manga_text_language: "ja",
          })
        }
      >
        manga-on
      </button>
      <button
        type="button"
        onClick={() =>
          // 設定モックはステートレスなので、V5 切替と漫画設定を 1 回の PUT で送る
          void ctx.updateSettings({
            image_model: "nai-diffusion-5-full",
            manga_mode: true,
            manga_panel_count: 3,
            manga_layout: "vertical",
            manga_text_language: "ja",
          })
        }
      >
        manga-on-v5
      </button>
      <button
        type="button"
        onClick={() =>
          ctx.restoreEntry({
            ...OLD_ENTRY,
            manga_mode: true,
            manga_panel_count: null,
          })
        }
      >
        restore-manga
      </button>
      <button type="button" onClick={() => ctx.addCharacterSlot("slot text")}>
        add-slot
      </button>
      <button type="button" onClick={() => void ctx.expandPositive()}>
        expand-positive
      </button>
      <button type="button" onClick={() => void ctx.expandNegative()}>
        expand-negative
      </button>
      <button type="button" onClick={() => void ctx.draftScript()}>
        draft-script
      </button>
      <button type="button" onClick={() => ctx.undoScriptDraft()}>
        undo-draft
      </button>
      <button
        type="button"
        onClick={() => {
          if (!ctx.pendingExpansion) return;
          ctx.applyExpansion(
            ctx.pendingExpansion.target === "positive"
              ? {
                  ...ctx.pendingExpansion,
                  positivePrompt: "edited prompt",
                  characterPrompts: ctx.pendingExpansion.characterPrompts
                    ? ["edited char"]
                    : null,
                }
              : { ...ctx.pendingExpansion, negativePrompt: "edited negative" },
          );
        }}
      >
        apply
      </button>
      <button
        type="button"
        onClick={() => {
          if (!ctx.pendingExpansion) return;
          void ctx.generateFromExpansion(
            ctx.pendingExpansion.target === "positive"
              ? {
                  ...ctx.pendingExpansion,
                  positivePrompt: "edited prompt",
                  characterPrompts: ctx.pendingExpansion.characterPrompts
                    ? ["edited char"]
                    : null,
                }
              : { ...ctx.pendingExpansion, negativePrompt: "edited negative" },
          );
        }}
      >
        generate-from
      </button>
      <button type="button" onClick={() => ctx.discardExpansion()}>
        discard
      </button>
      <button type="button" onClick={() => void ctx.runGenerate()}>
        run
      </button>
      <button type="button" onClick={() => ctx.restoreEntry(OLD_ENTRY)}>
        restore
      </button>
      <button
        type="button"
        onClick={() =>
          ctx.restoreEntry({
            ...OLD_ENTRY,
            positive_expand_mode: "off",
            instruction: "1girl, old prompt",
          })
        }
      >
        restore-plain
      </button>
      <button type="button" onClick={() => void ctx.regenerateEntry(OLD_ENTRY)}>
        regenerate
      </button>
      <button
        type="button"
        onClick={() =>
          void ctx.regenerateEntry({
            ...OLD_ENTRY,
            source_kind: "entry",
            source_entry_id: "entry-src",
          })
        }
      >
        regenerate-i2i
      </button>
      <button
        type="button"
        onClick={() =>
          void ctx.regenerateEntry({
            ...OLD_ENTRY,
            kind: "uploaded",
            final_prompt: "",
            positive_expand_mode: "off",
          })
        }
      >
        regenerate-uploaded
      </button>
      <button
        type="button"
        onClick={() => void ctx.suggestCharacters(2, "tags")}
      >
        suggest
      </button>
      <button type="button" onClick={() => void ctx.confirmUsageWarn(true)}>
        usage-confirm
      </button>
    </>
  );
}

function renderProvider() {
  return render(
    <MemoryRouter initialEntries={["/prompt-expander/sess-1"]}>
      <SettingsProvider>
        <NotificationProvider>
          <PromptExpanderProvider>
            <Probe />
          </PromptExpanderProvider>
        </NotificationProvider>
      </SettingsProvider>
    </MemoryRouter>,
  );
}

async function openSessionAndWait() {
  renderProvider();
  await waitFor(() =>
    expect(screen.getByTestId("settings-loaded").textContent).toBe("yes"),
  );
  fireEvent.click(screen.getByRole("button", { name: "open" }));
  await waitFor(() =>
    expect(screen.getByTestId("session").textContent).toBe("sess-1"),
  );
  await waitFor(() =>
    expect(screen.getByTestId("anlas").textContent).toBe("100"),
  );
}

async function clickAndWaitPending(name: string) {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name }));
  });
  await waitFor(() =>
    expect(screen.getByTestId("pending-expansion").textContent).not.toBe(
      "none",
    ),
  );
  return JSON.parse(
    screen.getByTestId("pending-expansion").textContent ?? "{}",
  );
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  calls.length = 0;
  fetchMock.mockClear();
  mockState.imageModel = "nai-diffusion-4-5-full";
  mockState.anlasUsagePercent = null;
  mockState.expandErrorCode = null;
  mockState.restoreSeed = false;
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PromptExpanderContext", () => {
  it("loads settings and session detail", async () => {
    await openSessionAndWait();
    expect(screen.getByTestId("image-model").textContent).toBe(
      "nai-diffusion-4-5-full",
    );
    expect(screen.getByTestId("entries").textContent).toBe("entry-old");
  });

  it("expandPositive posts /expand and sets pendingExpansion(target=positive) without generating", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    fireEvent.click(screen.getByRole("button", { name: "character-on" }));
    fireEvent.click(screen.getByRole("button", { name: "add-slot" }));

    const pending = await clickAndWaitPending("expand-positive");
    expect(pending.target).toBe("positive");
    expect(pending.mode).toBe("tags");
    expect(pending.instruction).toBe("a cat girl");
    expect(pending.positivePrompt).toBe("expanded: a cat girl");
    expect(pending.characterPrompts).toEqual([
      "expanded char 1",
      "expanded char 2",
    ]);
    expect(pending.negativePrompt).toBeNull();

    const expandCalls = findCalls("/prompt-expander/expand", "POST");
    expect(expandCalls).toHaveLength(1);
    const expandBody = JSON.parse(String(expandCalls[0].init?.body));
    expect(expandBody.instruction).toBe("a cat girl");
    expect(expandBody.expand_positive).toBe(true);
    expect(expandBody.expand_negative).toBe(false);
    expect(expandBody.character_mode).toBe(true);
    expect(expandBody.current_character_prompts).toEqual(["slot text"]);
    expect(expandBody.inherit_source_prompts).toBe(true);
    expect(expandBody).not.toHaveProperty("current_prompt");

    expect(findCalls("/generate", "POST")).toHaveLength(0);
    // 確認カードが開いている間は「生成」は押せない
    expect(screen.getByTestId("disabled-reason").textContent).toBe(
      "pending_expansion",
    );
  });

  it("applyExpansion writes the fields + origin, and runGenerate posts the expand metadata", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    fireEvent.click(screen.getByRole("button", { name: "character-on" }));
    await clickAndWaitPending("expand-positive");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "apply" }));
    });

    expect(screen.getByTestId("pending-expansion").textContent).toBe("none");
    expect(screen.getByTestId("positive").textContent).toBe("edited prompt");
    expect(screen.getByTestId("slots").textContent).toBe("edited char");
    expect(screen.getByTestId("character-mode").textContent).toBe("on");
    expect(
      JSON.parse(screen.getByTestId("positive-origin").textContent ?? "{}"),
    ).toEqual({ mode: "tags", instruction: "a cat girl" });
    expect(findCalls("/generate", "POST")).toHaveLength(0);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("entries").textContent).toBe(
        "entry-new,entry-old",
      ),
    );
    const body = lastBody("/generate", "POST");
    expect(body.prompt).toBe("edited prompt");
    expect(body.character_prompts).toEqual(["edited char"]);
    expect(body.character_mode).toBe(true);
    expect(body.positive_expand_mode).toBe("tags");
    expect(body.instruction).toBe("a cat girl");
    expect(body.negative_expand_mode).toBe("off");
    expect(body.source_kind).toBe("none");

    // 欄を空にすると拡張由来の印は消える
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "clear-positive" }));
    });
    expect(screen.getByTestId("positive-origin").textContent).toBe("none");
  });

  it("generateFromExpansion posts directly with the edited result and leaves the fields as-is", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    fireEvent.click(screen.getByRole("button", { name: "set-negative" }));
    fireEvent.click(screen.getByRole("button", { name: "positive-japanese" }));
    fireEvent.click(screen.getByRole("button", { name: "character-on" }));
    await clickAndWaitPending("expand-positive");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "generate-from" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("entries").textContent).toBe(
        "entry-new,entry-old",
      ),
    );
    // 確認カードは残す（同じ内容で繰り返す・微調整して再生成できる）
    expect(screen.getByTestId("pending-expansion").textContent).not.toBe(
      "none",
    );
    // 欄の内容は書き換えない（指示のまま）
    expect(screen.getByTestId("positive").textContent).toBe("a cat girl");
    expect(screen.getByTestId("positive-origin").textContent).toBe("none");

    const generateCalls = findCalls("/generate", "POST");
    expect(generateCalls).toHaveLength(1);
    const body = JSON.parse(String(generateCalls[0].init?.body));
    expect(body.prompt).toBe("edited prompt");
    expect(body.negative_prompt).toBe("blurry");
    expect(body.character_prompts).toEqual(["edited char"]);
    expect(body.character_mode).toBe(true);
    expect(body.positive_expand_mode).toBe("japanese");
    expect(body.negative_expand_mode).toBe("off");
    expect(body.instruction).toBe("a cat girl");

    // 残ったカードからもう一度生成できる。破棄すれば消える
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "generate-from" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(2));
    fireEvent.click(screen.getByRole("button", { name: "discard" }));
    expect(screen.getByTestId("pending-expansion").textContent).toBe("none");
  });

  it("generateFromExpansion saves the field content at click time as the instruction", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    await clickAndWaitPending("expand-positive");

    // 拡張後に原文を手直しした場合はその内容が原文として保存される
    fireEvent.click(screen.getByRole("button", { name: "set-positive-2" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "generate-from" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    expect(lastBody("/generate", "POST").instruction).toBe("a dog girl");

    // 欄を空にしたときは拡張時のスナップショットへ戻す
    fireEvent.click(screen.getByRole("button", { name: "clear-positive" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "generate-from" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(2));
    expect(lastBody("/generate", "POST").instruction).toBe("a cat girl");
  });

  it("expandNegative expands the negative field only, and applying it sets negativeOrigin", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    fireEvent.click(screen.getByRole("button", { name: "set-negative" }));

    const pending = await clickAndWaitPending("expand-negative");
    expect(pending.target).toBe("negative");
    expect(pending.mode).toBe("tags");
    expect(pending.positivePrompt).toBeNull();
    expect(pending.characterPrompts).toBeNull();
    expect(pending.negativePrompt).toBe("expanded negative: blurry");

    const expandBody = lastBody("/prompt-expander/expand", "POST");
    expect(expandBody.expand_positive).toBe(false);
    expect(expandBody.expand_negative).toBe(true);
    expect(expandBody.negative_instruction).toBe("blurry");
    expect(expandBody.negative_mode).toBe("tags");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "apply" }));
    });
    expect(screen.getByTestId("negative").textContent).toBe("edited negative");
    expect(screen.getByTestId("positive").textContent).toBe("a cat girl");
    expect(
      JSON.parse(screen.getByTestId("negative-origin").textContent ?? "{}"),
    ).toEqual({ mode: "tags" });
    expect(screen.getByTestId("positive-origin").textContent).toBe("none");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    const body = lastBody("/generate", "POST");
    expect(body.prompt).toBe("a cat girl");
    expect(body.negative_prompt).toBe("edited negative");
    expect(body.positive_expand_mode).toBe("off");
    expect(body.instruction).toBeNull();
    expect(body.negative_expand_mode).toBe("tags");
  });

  it("expansion failures surface as expansionError near the field instead of generating", async () => {
    mockState.expandErrorCode = "memory_empty";
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "expand-positive" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("expansion-error").textContent).not.toBe(
        "none",
      ),
    );
    const err = JSON.parse(
      screen.getByTestId("expansion-error").textContent ?? "{}",
    );
    expect(err.target).toBe("positive");
    expect(err.code).toBe("memory_empty");
    expect(screen.getByTestId("pending-expansion").textContent).toBe("none");
    expect(findCalls("/generate", "POST")).toHaveLength(0);

    // 空欄のまま拡張しようとした場合は API を呼ばずに理由を出す
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "expand-negative" }));
    });
    const err2 = JSON.parse(
      screen.getByTestId("expansion-error").textContent ?? "{}",
    );
    expect(err2.target).toBe("negative");
    expect(err2.code).toBe("empty_instruction");
    expect(findCalls("/prompt-expander/expand", "POST")).toHaveLength(1);
  });

  it("restoreEntry puts the original instruction back, rebuilds the expansion card and updates settings without the seed", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    await clickAndWaitPending("expand-positive");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "apply" }));
    });
    expect(screen.getByTestId("positive-origin").textContent).not.toBe("none");
    await clickAndWaitPending("expand-positive");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "restore" }));
    });

    // 拡張ありのエントリ: 原文を欄へ戻し、変換結果は確認カードとして再現する
    expect(screen.getByTestId("positive").textContent).toBe("old instruction");
    expect(screen.getByTestId("negative").textContent).toBe("lowres");
    expect(screen.getByTestId("character-mode").textContent).toBe("on");
    expect(screen.getByTestId("slots").textContent).toBe("girl A|girl B");
    expect(screen.getByTestId("positive-origin").textContent).toBe("none");
    expect(screen.getByTestId("negative-origin").textContent).toBe("none");
    expect(
      JSON.parse(screen.getByTestId("pending-expansion").textContent ?? "{}"),
    ).toEqual({
      target: "positive",
      mode: "tags",
      instruction: "old instruction",
      positivePrompt: "1girl, old prompt",
      characterPrompts: ["girl A", "girl B"],
      negativePrompt: null,
    });
    expect(screen.getByTestId("image-model").textContent).toBe(
      "nai-diffusion-5-full",
    );

    await waitFor(() => {
      const putCalls = findCalls("/prompt-expander/settings", "PUT");
      expect(putCalls.length).toBeGreaterThan(0);
      const body = JSON.parse(String(putCalls[putCalls.length - 1].init?.body));
      expect(body.image_model).toBe("nai-diffusion-5-full");
      expect(body.image_size).toBe("landscape");
      // restore_seed が OFF（既定）のときは seed に触れない
      expect(body).not.toHaveProperty("seed");
      expect(body.i2i_strength).toBe(0.7);
      expect(body.i2i_noise).toBe(0.2);
    });

    // 再現した確認カードからそのまま生成すると、原文と拡張モードのメタデータが付く
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "generate-from" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    const body = lastBody("/generate", "POST");
    expect(body.prompt).toBe("edited prompt");
    expect(body.positive_expand_mode).toBe("tags");
    expect(body.instruction).toBe("old instruction");
    expect(body.character_prompts).toEqual(["edited char"]);
  });

  it("restoreEntry restores the final prompt directly for entries generated without expansion", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    await clickAndWaitPending("expand-positive");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "restore-plain" }));
    });
    expect(screen.getByTestId("positive").textContent).toBe(
      "1girl, old prompt",
    );
    expect(screen.getByTestId("pending-expansion").textContent).toBe("none");

    // 復元した内容をそのまま生成すると拡張メタデータは付かない
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    const body = lastBody("/generate", "POST");
    expect(body.prompt).toBe("1girl, old prompt");
    expect(body.positive_expand_mode).toBe("off");
    expect(body.instruction).toBeNull();
    expect(body.character_prompts).toEqual(["girl A", "girl B"]);
  });

  it("restoreEntry copies the seed only when restore_seed is ON", async () => {
    mockState.restoreSeed = true;
    try {
      await openSessionAndWait();
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: "restore" }));
      });
      await waitFor(() => {
        const putCalls = findCalls("/prompt-expander/settings", "PUT");
        expect(putCalls.length).toBeGreaterThan(0);
        const body = JSON.parse(
          String(putCalls[putCalls.length - 1].init?.body),
        );
        expect(body.seed).toBe(12345);
        expect(body.image_model).toBe("nai-diffusion-5-full");
      });
    } finally {
      mockState.restoreSeed = false;
    }
  });

  it("regenerateEntry posts the entry's prompt and settings without a seed", async () => {
    await openSessionAndWait();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "regenerate" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    const body = lastBody("/generate", "POST");
    expect(body).not.toHaveProperty("seed");
    expect(body.prompt).toBe("1girl, old prompt");
    expect(body.negative_prompt).toBe("lowres");
    expect(body.character_prompts).toEqual(["girl A", "girl B"]);
    expect(body.character_mode).toBe(true);
    expect(body.instruction).toBe("old instruction");
    expect(body.positive_expand_mode).toBe("tags");
    expect(body.image_model).toBe("nai-diffusion-5-full");
    expect(body.image_size).toBe("landscape");
    expect(body.source_kind).toBe("none");
    expect(body).not.toHaveProperty("i2i_strength");
    expect(body.manga_mode).toBe(false);
    // 欄は触らない
    expect(screen.getByTestId("positive").textContent).toBe("");
    await waitFor(() =>
      expect(screen.getByTestId("entries").textContent).toBe(
        "entry-new,entry-old",
      ),
    );

    // 参照元がエントリなら同じ元で i2i する
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "regenerate-i2i" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(2));
    const i2iBody = lastBody("/generate", "POST");
    expect(i2iBody.source_kind).toBe("entry");
    expect(i2iBody.source_entry_id).toBe("entry-src");
    expect(i2iBody.i2i_strength).toBe(0.7);
    expect(i2iBody.i2i_noise).toBe(0.2);
    expect(i2iBody).not.toHaveProperty("seed");

    // プロンプトの無いアップロードは何も送らない
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "regenerate-uploaded" }),
      );
    });
    expect(findCalls("/generate", "POST")).toHaveLength(2);
  });

  it("characterMode is persisted to localStorage and restored on the next mount", async () => {
    await openSessionAndWait();
    expect(screen.getByTestId("character-mode").textContent).toBe("off");
    fireEvent.click(screen.getByRole("button", { name: "character-on" }));
    expect(screen.getByTestId("character-mode").textContent).toBe("on");
    expect(localStorage.getItem("prompt_expander_character_mode")).toBe("true");

    // 再マウント（再読み込み相当）でも ON のまま
    cleanup();
    await openSessionAndWait();
    expect(screen.getByTestId("character-mode").textContent).toBe("on");

    // 復元でスロットが無いエントリを戻すと OFF になり、それも保存される
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "restore-plain" }));
    });
    expect(screen.getByTestId("character-mode").textContent).toBe("on");
    expect(localStorage.getItem("prompt_expander_character_mode")).toBe("true");
  });

  it("draftScript rewrites the field into a notated storyboard and can be reverted", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "manga-on-v5" }));
    await waitFor(() =>
      expect(screen.getByTestId("manga-active").textContent).toBe("on"),
    );
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "draft-script" }));
    });
    await waitFor(() =>
      expect(findCalls("/prompt-expander/manga-script", "POST")).toHaveLength(
        1,
      ),
    );
    const body = lastBody("/prompt-expander/manga-script", "POST");
    expect(body).toMatchObject({
      instruction: "a cat girl",
      image_model: "nai-diffusion-5-full",
      text_model: "glm-4-6",
      language: "ja",
      manga: { panel_count: 3, layout: "vertical", narration: false },
    });
    await waitFor(() =>
      expect(screen.getByTestId("positive").textContent).toBe(
        "①a cat girl「え…？」\n②戸惑う『どうして…』",
      ),
    );
    expect(screen.getByTestId("drafting").textContent).toBe("no");
    expect(screen.getByTestId("draft-backup").textContent).toBe("a cat girl");

    // 元の文に戻せる
    fireEvent.click(screen.getByRole("button", { name: "undo-draft" }));
    expect(screen.getByTestId("positive").textContent).toBe("a cat girl");
    expect(screen.getByTestId("draft-backup").textContent).toBe("none");

    // 空欄では呼ばず、欄のそばのエラーになる
    fireEvent.click(screen.getByRole("button", { name: "clear-positive" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "draft-script" }));
    });
    expect(findCalls("/prompt-expander/manga-script", "POST")).toHaveLength(1);
    expect(
      JSON.parse(screen.getByTestId("expansion-error").textContent ?? "{}")
        .code,
    ).toBe("empty_instruction");
  });

  it("suggestCharacters sends the current input as input_text only when it is not empty", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "suggest" }));
    });
    await waitFor(() =>
      expect(findCalls("/suggest-characters", "POST")).toHaveLength(1),
    );
    expect(lastBody("/suggest-characters", "POST")).toMatchObject({
      text_model: "glm-4-6",
      image_model: "nai-diffusion-4-5-full",
      mode: "tags",
      count: 2,
      input_text: "a cat girl",
    });

    fireEvent.click(screen.getByRole("button", { name: "clear-positive" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "suggest" }));
    });
    await waitFor(() =>
      expect(findCalls("/suggest-characters", "POST")).toHaveLength(2),
    );
    expect(lastBody("/suggest-characters", "POST")).not.toHaveProperty(
      "input_text",
    );
  });

  it("manga mode is sent to /expand and /generate only while a V5 model is selected", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    // 日本語モードを選んでいても、漫画モード中はタグ扱いに固定される
    fireEvent.click(screen.getByRole("button", { name: "positive-japanese" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "manga-on" }));
    });
    // V4.5 のままでは漫画モードは効かない
    expect(screen.getByTestId("manga-active").textContent).toBe("off");
    let pending = await clickAndWaitPending("expand-positive");
    let expandBody = lastBody("/prompt-expander/expand", "POST");
    expect(expandBody.manga_mode).toBe(false);
    expect(expandBody).not.toHaveProperty("manga");
    expect(expandBody.positive_mode).toBe("japanese");
    expect(pending.mode).toBe("japanese");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "discard" }));
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "manga-on-v5" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("manga-active").textContent).toBe("on"),
    );
    pending = await clickAndWaitPending("expand-positive");
    expandBody = lastBody("/prompt-expander/expand", "POST");
    expect(expandBody.manga_mode).toBe(true);
    expect(expandBody.positive_mode).toBe("tags");
    expect(pending.mode).toBe("tags");
    expect(expandBody.manga).toEqual({
      panel_count: 3,
      layout: "vertical",
      dialogue: true,
      text_language: "ja",
      sound_effects: true,
      reading_direction: "rtl",
      narration: false,
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "generate-from" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    const body = lastBody("/generate", "POST");
    expect(body.manga_mode).toBe(true);
    expect(body.manga_panel_count).toBe(3);
  });

  it("restoreEntry restores the manga flag (null panel count = auto)", async () => {
    await openSessionAndWait();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "restore-manga" }));
    });
    await waitFor(() => {
      const putCalls = findCalls("/prompt-expander/settings", "PUT");
      expect(putCalls.length).toBeGreaterThan(0);
      const body = JSON.parse(String(putCalls[putCalls.length - 1].init?.body));
      expect(body.manga_mode).toBe(true);
      expect(body.manga_panel_count).toBe(0);
    });
    await waitFor(() =>
      expect(screen.getByTestId("manga-active").textContent).toBe("on"),
    );
  });

  it("V5 usage exhausted gating sets pendingUsageWarn and respects the sessionStorage key", async () => {
    mockState.imageModel = "nai-diffusion-5-full";
    mockState.anlasUsagePercent = 0;
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });

    await waitFor(() =>
      expect(screen.getByTestId("pending-usage").textContent).toBe("yes"),
    );
    expect(findCalls("/generate", "POST")).toHaveLength(0);

    // 確認（抑止 ON）→ 生成が走り、sessionStorage にキーが保存される
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "usage-confirm" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("entries").textContent).toBe(
        "entry-new,entry-old",
      ),
    );
    expect(screen.getByTestId("pending-usage").textContent).toBe("no");
    expect(sessionStorage.getItem(V5_USAGE_WARN_SUPPRESSED_KEY)).toBe("true");

    // 抑止キーがある状態では確認ダイアログを出さずに直接生成する
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(2));
    expect(screen.getByTestId("pending-usage").textContent).toBe("no");
  });
});
