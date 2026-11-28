import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PromptExpanderEntry } from "../../apis/promptExpander";
import { V5_USAGE_WARN_SUPPRESSED_KEY } from "../../constants/novelaiImageModels";
import { PROMPT_EXPANDER_ANLAS_WARN_SUPPRESSED_KEY } from "../../constants/promptExpander";
import { NotificationProvider, useNotification } from "../NotificationContext";
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
  /** 生成の応答をこの Promise が解けるまで待たせる（null なら待たない） */
  generateGate: Promise<void> | null;
  /** 生成をこのエラーコードで失敗させる（null なら成功） */
  generateErrorCode: string | null;
  /** /expand と /manga-script の応答をこの Promise が解けるまで待たせる（null なら待たない） */
  llmGate: Promise<void> | null;
  /** セッション詳細の応答を、ID ごとにこの Promise が解けるまで待たせる */
  sessionGates: Partial<Record<string, Promise<void>>>;
  /** セッション名の保存をこのエラーコードで失敗させる（null なら成功） */
  renameErrorCode: string | null;
}

const mockState: MockState = {
  imageModel: "nai-diffusion-4-5-full",
  anlasUsagePercent: null,
  expandErrorCode: null,
  restoreSeed: false,
  generateGate: null,
  generateErrorCode: null,
  llmGate: null,
  sessionGates: {},
  renameErrorCode: null,
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
      use_precise_reference: false,
      transparent_background: false,
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
    reference_types: ["character", "style", "character&style"],
    anlas_per_reference: 5,
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
  transparent_background: false,
  references: [],
  inpaint: false,
  mask_url: null,
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
    if (url === "/api/game/character-presets/preset-1") {
      return jsonResponse({
        id: "preset-1",
        name: "サクラ",
        appearance_tags: "1girl, pink hair (preset)",
        portrait_url: "/game/character-presets/preset-1/images/portrait.png",
        thumbnail_url: null,
      });
    }
    if (url === "/api/game/character-presets/preset-gone") {
      return jsonResponse({ detail: { code: "preset_not_found" } }, 404);
    }
    if (url === "/api/game/anlas") {
      return jsonResponse(anlasPayload());
    }
    if (url === "/api/prompt-expander/sessions/sess-1" && method === "GET") {
      if (mockState.sessionGates["sess-1"]) {
        await mockState.sessionGates["sess-1"];
      }
      return jsonResponse({ session: SESSION, entries: [OLD_ENTRY] });
    }
    if (url === "/api/prompt-expander/sessions/sess-1" && method === "PATCH") {
      if (mockState.renameErrorCode) {
        return jsonResponse(
          {
            detail: {
              code: mockState.renameErrorCode,
              message: `failed: ${mockState.renameErrorCode}`,
            },
          },
          503,
        );
      }
      const body = JSON.parse(String(init?.body));
      return jsonResponse({ ...SESSION, title: body.title });
    }
    if (url === "/api/prompt-expander/sessions/sess-2" && method === "GET") {
      if (mockState.sessionGates["sess-2"]) {
        await mockState.sessionGates["sess-2"];
      }
      return jsonResponse({
        session: { ...SESSION, id: "sess-2", title: "Other", entry_count: 0 },
        entries: [],
      });
    }
    if (url === "/api/prompt-expander/expand" && method === "POST") {
      if (mockState.llmGate) await mockState.llmGate;
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
      if (mockState.llmGate) await mockState.llmGate;
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
      if (mockState.generateGate) await mockState.generateGate;
      if (mockState.generateErrorCode) {
        return jsonResponse(
          {
            detail: {
              code: mockState.generateErrorCode,
              message: `failed: ${mockState.generateErrorCode}`,
            },
          },
          502,
        );
      }
      return jsonResponse({
        entry: makeGeneratedEntry(body),
        anlas: anlasPayload(),
      });
    }
    if (
      url.startsWith("/api/prompt-expander/entries/") &&
      method === "DELETE"
    ) {
      return jsonResponse({ ok: true });
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
  const { notifications } = useNotification();
  const [renameResult, setRenameResult] = useState("none");
  return (
    <>
      <div data-testid="session-title">{ctx.activeSession?.title ?? ""}</div>
      <div data-testid="rename-result">{renameResult}</div>
      <button
        type="button"
        onClick={() =>
          void ctx
            .renameSession("sess-1", "New name")
            .then((ok) => setRenameResult(ok ? "saved" : "failed"))
        }
      >
        rename
      </button>
      <div data-testid="pending-negative-prompt">
        {ctx.negativeExpansion?.negativePrompt ?? "none"}
      </div>
      <button
        type="button"
        onClick={() => ctx.editNegativeExpansion("hand edited")}
      >
        edit-card
      </button>
      <div data-testid="instruction">{ctx.instructionText}</div>
      <div data-testid="script">{ctx.scriptText}</div>
      <div data-testid="prompt-undo">
        {ctx.promptUndo ? ctx.promptUndo.prompt : "none"}
      </div>
      <div data-testid="script-undo">
        {ctx.scriptUndo ? ctx.scriptUndo.script : "none"}
      </div>
      <div data-testid="input-mode">{ctx.promptInputMode}</div>
      <button
        type="button"
        onClick={() => ctx.setInstructionText("a cat girl")}
      >
        set-instruction
      </button>
      <button
        type="button"
        onClick={() => ctx.setInstructionText("a dog girl")}
      >
        set-instruction-2
      </button>
      <button type="button" onClick={() => ctx.setInstructionText("")}>
        clear-instruction
      </button>
      <button
        type="button"
        onClick={() => ctx.setScriptText("①鏡を見る「え」")}
      >
        set-script
      </button>
      <button
        type="button"
        onClick={() => ctx.setPositiveText("edited prompt")}
      >
        edit-prompt
      </button>
      <button type="button" onClick={() => ctx.setPromptInputMode("direct")}>
        input-direct
      </button>
      <button type="button" onClick={() => void ctx.expandPositive("script")}>
        expand-script
      </button>
      <button type="button" onClick={() => ctx.undoPrompt()}>
        undo-prompt
      </button>
      <div data-testid="notifications">
        {notifications.map((n) => n.title).join("|")}
      </div>
      <div data-testid="reference-count">{ctx.references.length}</div>
      <div data-testid="reference-cost">{ctx.referenceAnlasCost}</div>
      <div data-testid="reference-cast">
        {JSON.stringify(ctx.referenceCast)}
      </div>
      <div data-testid="reference-detail">
        {JSON.stringify(
          ctx.references.map((r) => ({
            kind: r.kind,
            type: r.type,
            strength: r.strength,
            includeOutfit: r.includeOutfit,
            name: r.name,
            appearanceTags: r.appearanceTags,
            thumbnailUrl: r.thumbnailUrl,
          })),
        )}
      </div>
      <div data-testid="session">{ctx.activeSession?.id ?? "none"}</div>
      <div data-testid="settings-loaded">
        {ctx.settingsLoaded ? "yes" : "no"}
      </div>
      <div data-testid="image-model">{ctx.settings.image_model}</div>
      <div data-testid="entries">{ctx.entries.map((e) => e.id).join(",")}</div>
      <div data-testid="pending-expansion">
        {ctx.negativeExpansion ? JSON.stringify(ctx.negativeExpansion) : "none"}
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
      <div data-testid="character-mode">{ctx.characterMode ? "on" : "off"}</div>
      <div data-testid="manga-active">{ctx.mangaActive ? "on" : "off"}</div>
      <div data-testid="reference-active">
        {ctx.referenceActive ? "on" : "off"}
      </div>
      <div data-testid="transparent-active">
        {ctx.transparentActive ? "on" : "off"}
      </div>
      <div data-testid="pending-reference">
        {ctx.pendingReferenceWarn ? "yes" : "no"}
      </div>
      <div data-testid="slots">{ctx.characterSlots.join("|")}</div>
      <div data-testid="anlas">{ctx.anlas ? ctx.anlas.totalAnlas : "none"}</div>
      <div data-testid="error">{ctx.error ?? ""}</div>
      <div data-testid="disabled-reason">
        {ctx.generateDisabledReason ?? "none"}
      </div>
      <button type="button" onClick={() => void ctx.openSession("sess-1")}>
        open
      </button>
      <button type="button" onClick={() => void ctx.openSession("sess-2")}>
        open-2
      </button>
      <div data-testid="generating-session">
        {ctx.generatingSessionId ?? "none"}
      </div>
      <div data-testid="outcome">
        {ctx.lastGenerateOutcome
          ? JSON.stringify(ctx.lastGenerateOutcome)
          : "none"}
      </div>
      <div data-testid="session-counts">
        {ctx.sessions.map((s) => `${s.id}:${s.entry_count}`).join(",")}
      </div>
      <div data-testid="restore-undo">
        {ctx.restoreUndo ? ctx.restoreUndo.restoredPositive : "none"}
      </div>
      <button type="button" onClick={ctx.undoRestore}>
        undo-restore
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
      <button
        type="button"
        onClick={() => void ctx.expandPositive("instruction")}
      >
        expand-positive
      </button>
      <button type="button" onClick={() => void ctx.expandNegative()}>
        expand-negative
      </button>
      <button type="button" onClick={() => void ctx.draftScript()}>
        draft-script
      </button>
      <div data-testid="story-context">
        {ctx.storyContextEntryIds.join(",")}
      </div>
      <button
        type="button"
        onClick={() => ctx.toggleStoryContextEntry("entry-new")}
      >
        story-toggle-new
      </button>
      <button
        type="button"
        onClick={() => ctx.toggleStoryContextEntry("entry-old")}
      >
        story-toggle-old
      </button>
      <button type="button" onClick={() => ctx.clearStoryContext()}>
        story-clear
      </button>
      <button type="button" onClick={() => void ctx.deleteEntry("entry-old")}>
        delete-old
      </button>
      <button
        type="button"
        onClick={() => void ctx.updateSettings({ manga_mode: false })}
      >
        manga-off
      </button>
      <button type="button" onClick={() => ctx.undoScript()}>
        undo-draft
      </button>
      <button type="button" onClick={() => ctx.applyNegativeExpansion()}>
        apply
      </button>
      <button
        type="button"
        onClick={() => void ctx.generateFromNegativeExpansion()}
      >
        generate-from
      </button>
      <button type="button" onClick={() => ctx.discardNegativeExpansion()}>
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
      <button
        type="button"
        onClick={() =>
          ctx.restoreEntry({
            ...OLD_ENTRY,
            instruction: "①鏡を見る「え」",
            synopsis: "朝起きたら女の子になっていた",
            manga_mode: true,
          })
        }
      >
        restore-script
      </button>
      <button
        type="button"
        onClick={() =>
          ctx.restoreEntry({
            ...OLD_ENTRY,
            instruction: "①鏡を見る「え」",
            synopsis: null,
            instruction_source: "script",
            manga_mode: true,
          })
        }
      >
        restore-handwritten-script
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
      <button
        type="button"
        onClick={() => void ctx.updateSettings({ use_precise_reference: true })}
      >
        reference-on
      </button>
      <button
        type="button"
        onClick={() =>
          // 設定モックはステートレスなので、V5 切替と参照 ON を 1 回の PUT で送る
          void ctx.updateSettings({
            image_model: "nai-diffusion-5-full",
            use_precise_reference: true,
          })
        }
      >
        reference-on-v5
      </button>
      <button
        type="button"
        onClick={() => {
          const first = ctx.references[0];
          if (first) {
            ctx.updateReference(first.id, {
              type: "costume",
              includeOutfit: true,
              strength: 3,
            });
          }
        }}
      >
        reference-v5-options
      </button>
      <button
        type="button"
        onClick={() =>
          ctx.addReference({
            kind: "character",
            characterPresetId: "preset-1",
            thumbnailUrl: "/api/game/character-presets/preset-1/portrait.png",
            label: "サクラ",
            name: "サクラ",
            appearanceTags: "1girl, pink hair",
          })
        }
      >
        add-character-reference
      </button>
      <button
        type="button"
        onClick={() =>
          ctx.addReference({
            kind: "upload",
            uploadDataUrl: "data:image/png;base64,AAAA",
            thumbnailUrl: "data:image/png;base64,AAAA",
            label: "upload.png",
            name: "ユイ",
            appearanceTags: "1girl, black hair",
          })
        }
      >
        add-upload-reference
      </button>
      <button
        type="button"
        onClick={() => {
          const first = ctx.references[0];
          if (first) ctx.updateReference(first.id, { type: "style" });
        }}
      >
        first-reference-style
      </button>
      <button
        type="button"
        onClick={() =>
          // 設定モックはステートレスなので、漫画モードと参照 ON を 1 回の PUT で送る
          void ctx.updateSettings({
            image_model: "nai-diffusion-5-full",
            manga_mode: true,
            use_precise_reference: true,
          })
        }
      >
        manga-reference-on-v5
      </button>
      <button
        type="button"
        onClick={() =>
          void ctx.updateSettings({
            image_model: "nai-diffusion-5-full-medium",
            use_precise_reference: true,
          })
        }
      >
        reference-on-economy
      </button>
      <button
        type="button"
        onClick={() =>
          ctx.addReference({
            kind: "entry",
            entryId: "entry-ref",
            thumbnailUrl: "/api/prompt-expander/images/entry-ref",
            label: "ref",
          })
        }
      >
        set-reference
      </button>
      <button type="button" onClick={() => void ctx.confirmReferenceWarn(true)}>
        reference-confirm
      </button>
      <button
        type="button"
        onClick={() =>
          void ctx.updateSettings({ transparent_background: true })
        }
      >
        transparent-on
      </button>
      <button
        type="button"
        onClick={() =>
          void ctx.updateSettings({
            image_model: "nai-diffusion-5-full",
            manga_mode: true,
            transparent_background: true,
          })
        }
      >
        transparent-on-manga-v5
      </button>
      <button
        type="button"
        onClick={() =>
          ctx.restoreEntry({
            ...OLD_ENTRY,
            transparent_background: true,
            references: [
              {
                kind: "entry",
                history_id: null,
                entry_id: "entry-ref",
                character_preset_id: null,
                type: "style",
                include_outfit: null,
                strength: 0.5,
                fidelity: 0.75,
                name: null,
              },
              {
                kind: "character",
                history_id: null,
                entry_id: null,
                character_preset_id: "preset-1",
                type: "character",
                include_outfit: true,
                strength: 0.5,
                fidelity: null,
                name: "サクラ",
                appearance_tags: "1girl, pink hair",
              },
              {
                kind: "character",
                history_id: null,
                entry_id: null,
                character_preset_id: "preset-gone",
                type: "character",
                include_outfit: false,
                strength: 0.5,
                fidelity: null,
                name: "ユイ",
              },
              {
                kind: "upload",
                history_id: null,
                entry_id: null,
                character_preset_id: null,
                type: "character",
                include_outfit: false,
                strength: 0.85,
                fidelity: null,
                name: null,
              },
            ],
          })
        }
      >
        restore-ref
      </button>
      <button
        type="button"
        onClick={() =>
          void ctx.regenerateEntry({
            ...OLD_ENTRY,
            image_model: "nai-diffusion-4-5-full",
            transparent_background: true,
            references: [
              {
                kind: "entry",
                history_id: null,
                entry_id: "entry-ref",
                character_preset_id: null,
                type: "style",
                include_outfit: null,
                strength: 0.5,
                fidelity: 0.75,
                name: null,
              },
            ],
          })
        }
      >
        regenerate-ref
      </button>
      <button
        type="button"
        onClick={() =>
          void ctx.regenerateEntry({
            ...OLD_ENTRY,
            image_model: "nai-diffusion-5-full",
            references: [
              {
                kind: "upload",
                history_id: null,
                entry_id: null,
                character_preset_id: null,
                type: "character",
                include_outfit: false,
                strength: 0.85,
                fidelity: null,
                name: null,
              },
              {
                kind: "character",
                history_id: null,
                entry_id: null,
                character_preset_id: "preset-1",
                type: "character",
                include_outfit: true,
                strength: 0.5,
                fidelity: null,
                name: "サクラ",
              },
            ],
          })
        }
      >
        regenerate-ref-upload
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

/** プロンプト化（結果はプロンプト欄へ直接入る）を押して、終わるまで待つ */
async function convertAndWait(name = "expand-positive") {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name }));
  });
  await waitFor(() =>
    expect(screen.getByTestId("expanding").textContent).toBe("none"),
  );
}

/** ネガティブ欄の変換カードが出るまで待ち、その内容を返す */
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
  mockState.generateGate = null;
  mockState.generateErrorCode = null;
  mockState.llmGate = null;
  mockState.sessionGates = {};
  mockState.renameErrorCode = null;
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

  it("expandPositive puts the prompt into the prompt field and keeps the instruction", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    fireEvent.click(screen.getByRole("button", { name: "character-on" }));
    fireEvent.click(screen.getByRole("button", { name: "add-slot" }));

    await convertAndWait();
    // 結果はプロンプト欄（とキャラ枠）へ直接入り、指示の欄はそのまま残る
    expect(screen.getByTestId("positive").textContent).toBe(
      "expanded: a cat girl",
    );
    expect(screen.getByTestId("instruction").textContent).toBe("a cat girl");
    expect(screen.getByTestId("slots").textContent).toBe(
      "expanded char 1|expanded char 2",
    );
    expect(
      JSON.parse(screen.getByTestId("positive-origin").textContent ?? "{}"),
    ).toEqual({
      mode: "tags",
      instruction: "a cat girl",
      source: "instruction",
      synopsis: null,
    });
    // 前のプロンプトは空だったので、元に戻す用の控えは無い
    expect(screen.getByTestId("prompt-undo").textContent).toBe("none");

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

    // 生成はしない。確認カードは無いので、そのまま生成できる
    expect(findCalls("/generate", "POST")).toHaveLength(0);
    expect(screen.getByTestId("disabled-reason").textContent).toBe("none");
  });

  it("a converted prompt is generated with the instruction it was made from", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    fireEvent.click(screen.getByRole("button", { name: "character-on" }));
    await convertAndWait();
    // プロンプト欄を手直ししても、元にした指示の印は残る
    fireEvent.click(screen.getByRole("button", { name: "edit-prompt" }));

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
    expect(body.character_prompts).toEqual([
      "expanded char 1",
      "expanded char 2",
    ]);
    expect(body.character_mode).toBe(true);
    expect(body.positive_expand_mode).toBe("tags");
    expect(body.instruction).toBe("a cat girl");
    expect(body.synopsis).toBeNull();
    expect(body.negative_expand_mode).toBe("off");
    expect(body.source_kind).toBe("none");

    // プロンプト欄を空にすると、LLM で作った印は消える
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "clear-positive" }));
    });
    expect(screen.getByTestId("positive-origin").textContent).toBe("none");
  });

  it("creating the prompt again keeps the previous prompt so it can be undone", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    await convertAndWait();
    fireEvent.click(screen.getByRole("button", { name: "edit-prompt" }));

    fireEvent.click(screen.getByRole("button", { name: "set-instruction-2" }));
    await convertAndWait();
    expect(screen.getByTestId("positive").textContent).toBe(
      "expanded: a dog girl",
    );
    expect(screen.getByTestId("prompt-undo").textContent).toBe("edited prompt");

    // 元に戻すと、手直ししたプロンプトと、それを作った指示の印が戻る
    fireEvent.click(screen.getByRole("button", { name: "undo-prompt" }));
    expect(screen.getByTestId("positive").textContent).toBe("edited prompt");
    expect(
      JSON.parse(screen.getByTestId("positive-origin").textContent ?? "{}")
        .instruction,
    ).toBe("a cat girl");
    expect(screen.getByTestId("prompt-undo").textContent).toBe("none");
  });

  it("records the text the prompt was made from even after the instruction is edited", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    await convertAndWait();

    // 作ったあとで指示を書き換えても、送るのは作ったプロンプトなので、履歴の原文もその元の文にする
    fireEvent.click(screen.getByRole("button", { name: "set-instruction-2" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    expect(lastBody("/generate", "POST").instruction).toBe("a cat girl");
    expect(screen.getByTestId("instruction").textContent).toBe("a dog girl");
  });

  it("expandNegative expands the negative field only, and applying it sets negativeOrigin", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    fireEvent.click(screen.getByRole("button", { name: "set-negative" }));

    const pending = await clickAndWaitPending("expand-negative");
    expect(pending).toEqual({
      mode: "tags",
      negativePrompt: "expanded negative: blurry",
    });

    const expandBody = lastBody("/prompt-expander/expand", "POST");
    expect(expandBody.expand_positive).toBe(false);
    expect(expandBody.expand_negative).toBe(true);
    expect(expandBody.negative_instruction).toBe("blurry");
    expect(expandBody.negative_mode).toBe("tags");
    // ネガティブのカードを確かめるまでは生成できない
    expect(screen.getByTestId("disabled-reason").textContent).toBe(
      "pending_expansion",
    );

    fireEvent.click(screen.getByRole("button", { name: "edit-card" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "apply" }));
    });
    expect(screen.getByTestId("negative").textContent).toBe("hand edited");
    expect(screen.getByTestId("positive").textContent).toBe("a cat girl");
    expect(
      JSON.parse(screen.getByTestId("negative-origin").textContent ?? "{}"),
    ).toEqual({ mode: "tags" });
    expect(screen.getByTestId("positive-origin").textContent).toBe("none");
    expect(screen.getByTestId("pending-expansion").textContent).toBe("none");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    const body = lastBody("/generate", "POST");
    expect(body.prompt).toBe("a cat girl");
    expect(body.negative_prompt).toBe("hand edited");
    expect(body.positive_expand_mode).toBe("off");
    expect(body.instruction).toBeNull();
    expect(body.negative_expand_mode).toBe("tags");
  });

  it("generateFromNegativeExpansion generates with the card and keeps it", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    fireEvent.click(screen.getByRole("button", { name: "set-negative" }));
    await clickAndWaitPending("expand-negative");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "generate-from" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    const body = lastBody("/generate", "POST");
    expect(body.prompt).toBe("a cat girl");
    expect(body.negative_prompt).toBe("expanded negative: blurry");
    expect(body.negative_expand_mode).toBe("tags");
    // 欄は変えず、カードは残す（微調整して再生成できる）。破棄すれば消える
    expect(screen.getByTestId("negative").textContent).toBe("blurry");
    expect(screen.getByTestId("pending-expansion").textContent).not.toBe(
      "none",
    );
    fireEvent.click(screen.getByRole("button", { name: "discard" }));
    expect(screen.getByTestId("pending-expansion").textContent).toBe("none");
  });

  it("expansion failures surface as expansionError near the field instead of generating", async () => {
    mockState.expandErrorCode = "memory_empty";
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));

    await convertAndWait();
    const err = JSON.parse(
      screen.getByTestId("expansion-error").textContent ?? "{}",
    );
    expect(err.target).toBe("positive");
    expect(err.field).toBe("instruction");
    expect(err.code).toBe("memory_empty");
    expect(screen.getByTestId("positive").textContent).toBe("");
    expect(findCalls("/generate", "POST")).toHaveLength(0);

    // 空のネーム欄からプロンプト化しようとした場合は API を呼ばずに、その欄のそばに理由を出す
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "expand-script" }));
    });
    const err2 = JSON.parse(
      screen.getByTestId("expansion-error").textContent ?? "{}",
    );
    expect(err2).toMatchObject({
      target: "positive",
      field: "script",
      code: "empty_instruction",
    });

    // ネガティブ欄も同じ
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "expand-negative" }));
    });
    const err3 = JSON.parse(
      screen.getByTestId("expansion-error").textContent ?? "{}",
    );
    expect(err3.target).toBe("negative");
    expect(err3.code).toBe("empty_instruction");
    expect(findCalls("/prompt-expander/expand", "POST")).toHaveLength(1);
  });

  it("restoreEntry puts the instruction and the prompt into their own fields and updates settings without the seed", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    await convertAndWait();
    fireEvent.click(screen.getByRole("button", { name: "input-direct" }));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "restore" }));
    });

    // 拡張ありのエントリ: 指示を指示欄へ、最終プロンプトをプロンプト欄へ戻す
    expect(screen.getByTestId("instruction").textContent).toBe(
      "old instruction",
    );
    expect(screen.getByTestId("script").textContent).toBe("");
    expect(screen.getByTestId("positive").textContent).toBe(
      "1girl, old prompt",
    );
    expect(screen.getByTestId("negative").textContent).toBe("lowres");
    expect(screen.getByTestId("character-mode").textContent).toBe("on");
    expect(screen.getByTestId("slots").textContent).toBe("girl A|girl B");
    expect(
      JSON.parse(screen.getByTestId("positive-origin").textContent ?? "{}"),
    ).toEqual({
      mode: "tags",
      instruction: "old instruction",
      source: "instruction",
      synopsis: null,
    });
    expect(screen.getByTestId("negative-origin").textContent).toBe("none");
    expect(screen.getByTestId("pending-expansion").textContent).toBe("none");
    // 直接書くのままだと戻した指示が見えないので、LLM で作るへ切り替える
    expect(screen.getByTestId("input-mode").textContent).toBe("assist");
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

    // 復元した内容をそのまま生成すると、元の文と拡張モードのメタデータが付く
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    const body = lastBody("/generate", "POST");
    expect(body.prompt).toBe("1girl, old prompt");
    expect(body.positive_expand_mode).toBe("tags");
    expect(body.instruction).toBe("old instruction");
    expect(body.synopsis).toBeNull();
    expect(body.instruction_source).toBe("instruction");
    expect(body.character_prompts).toEqual(["girl A", "girl B"]);
  });

  it("restoreEntry puts a storyboard entry back as synopsis, storyboard and prompt", async () => {
    await openSessionAndWait();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "restore-script" }));
    });
    expect(screen.getByTestId("instruction").textContent).toBe(
      "朝起きたら女の子になっていた",
    );
    expect(screen.getByTestId("script").textContent).toBe("①鏡を見る「え」");
    expect(screen.getByTestId("positive").textContent).toBe(
      "1girl, old prompt",
    );
    expect(
      JSON.parse(screen.getByTestId("positive-origin").textContent ?? "{}"),
    ).toEqual({
      mode: "tags",
      instruction: "①鏡を見る「え」",
      source: "script",
      synopsis: "朝起きたら女の子になっていた",
    });

    // そのまま生成すると、ネームとあらすじを分けて送る
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    const body = lastBody("/generate", "POST");
    expect(body.instruction).toBe("①鏡を見る「え」");
    expect(body.synopsis).toBe("朝起きたら女の子になっていた");
  });

  it("restoreEntry puts a storyboard written by hand without a synopsis back into the storyboard field", async () => {
    await openSessionAndWait();
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "restore-handwritten-script" }),
      );
    });
    expect(screen.getByTestId("instruction").textContent).toBe("");
    expect(screen.getByTestId("script").textContent).toBe("①鏡を見る「え」");
    expect(
      JSON.parse(screen.getByTestId("positive-origin").textContent ?? "{}"),
    ).toEqual({
      mode: "tags",
      instruction: "①鏡を見る「え」",
      source: "script",
      synopsis: null,
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    expect(lastBody("/generate", "POST")).toMatchObject({
      instruction: "①鏡を見る「え」",
      synopsis: null,
      instruction_source: "script",
    });
  });

  it("restoreEntry restores the final prompt directly for entries generated without expansion", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    await convertAndWait();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "restore-plain" }));
    });
    expect(screen.getByTestId("positive").textContent).toBe(
      "1girl, old prompt",
    );
    // 指示から作っていないので、指示欄は空にする
    expect(screen.getByTestId("instruction").textContent).toBe("");
    expect(screen.getByTestId("positive-origin").textContent).toBe("none");

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

  it("draftScript puts a notated storyboard into the storyboard field and keeps the synopsis", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "manga-on-v5" }));
    await waitFor(() =>
      expect(screen.getByTestId("manga-active").textContent).toBe("on"),
    );
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
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
      expect(screen.getByTestId("script").textContent).toBe(
        "①a cat girl「え…？」\n②戸惑う『どうして…』",
      ),
    );
    // あらすじは書き換えない
    expect(screen.getByTestId("instruction").textContent).toBe("a cat girl");
    expect(screen.getByTestId("drafting").textContent).toBe("no");
    expect(screen.getByTestId("script-undo").textContent).toBe("");

    // ネームからプロンプトを作ると、ネームとあらすじを分けて記録する
    await convertAndWait("expand-script");
    expect(lastBody("/prompt-expander/expand", "POST").instruction).toBe(
      "①a cat girl「え…？」\n②戸惑う『どうして…』",
    );
    expect(
      JSON.parse(screen.getByTestId("positive-origin").textContent ?? "{}"),
    ).toMatchObject({ source: "script", synopsis: "a cat girl" });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    expect(lastBody("/generate", "POST")).toMatchObject({
      instruction: "①a cat girl「え…？」\n②戸惑う『どうして…』",
      synopsis: "a cat girl",
      instruction_source: "script",
    });

    // 手で書いたネームの上に下書きし直しても、元に戻せる
    fireEvent.click(screen.getByRole("button", { name: "set-script" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "draft-script" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("script-undo").textContent).toBe(
        "①鏡を見る「え」",
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "undo-draft" }));
    expect(screen.getByTestId("script").textContent).toBe("①鏡を見る「え」");
    expect(screen.getByTestId("script-undo").textContent).toBe("none");

    // あらすじが空なら呼ばず、あらすじ欄のそばのエラーになる
    fireEvent.click(screen.getByRole("button", { name: "clear-instruction" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "draft-script" }));
    });
    expect(findCalls("/prompt-expander/manga-script", "POST")).toHaveLength(2);
    expect(
      JSON.parse(screen.getByTestId("expansion-error").textContent ?? "{}"),
    ).toMatchObject({ field: "instruction", code: "empty_instruction" });
  });

  it("story so far: picked pages are sent in creation order to /manga-script and comic /expand, and kept in the session draft", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "manga-on-v5" }));
    await waitFor(() =>
      expect(screen.getByTestId("manga-active").textContent).toBe("on"),
    );
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    // 2 ページ目を作っておく（entry-new は entry-old より後に生成）
    await convertAndWait();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("entries").textContent).toBe(
        "entry-new,entry-old",
      ),
    );

    // 選んだ順ではなく、生成した順（話の順）に並ぶ
    fireEvent.click(screen.getByRole("button", { name: "story-toggle-new" }));
    fireEvent.click(screen.getByRole("button", { name: "story-toggle-old" }));
    expect(screen.getByTestId("story-context").textContent).toBe(
      "entry-old,entry-new",
    );

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "draft-script" }));
    });
    await waitFor(() =>
      expect(findCalls("/prompt-expander/manga-script", "POST")).toHaveLength(
        1,
      ),
    );
    expect(
      lastBody("/prompt-expander/manga-script", "POST").context_entry_ids,
    ).toEqual(["entry-old", "entry-new"]);
    await convertAndWait("expand-script");
    expect(
      lastBody("/prompt-expander/expand", "POST").context_entry_ids,
    ).toEqual(["entry-old", "entry-new"]);

    // もう一度押すと外れる
    fireEvent.click(screen.getByRole("button", { name: "story-toggle-new" }));
    expect(screen.getByTestId("story-context").textContent).toBe("entry-old");

    // 漫画モードでないプロンプト化には送らない（選択は残る）
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "manga-off" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("manga-active").textContent).toBe("off"),
    );
    await convertAndWait();
    expect(lastBody("/prompt-expander/expand", "POST")).not.toHaveProperty(
      "context_entry_ids",
    );
    expect(screen.getByTestId("story-context").textContent).toBe("entry-old");

    // 再読み込みしても書きかけとして残る
    cleanup();
    await openSessionAndWait();
    await waitFor(() =>
      expect(screen.getByTestId("story-context").textContent).toBe("entry-old"),
    );

    // エントリを消すと外れる
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "delete-old" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("entries").textContent).toBe(""),
    );
    expect(screen.getByTestId("story-context").textContent).toBe("");
  });

  it("story so far stops at the page limit and ignores pages no longer in the list", async () => {
    // 一覧に無い ID（ほかのタブで消した等）が書きかけに残っていても、表示・送信に使わず上限にも数えない
    sessionStorage.setItem(
      "prompt_expander_draft:sess-1",
      JSON.stringify({
        version: 2,
        instructionText: "a cat girl",
        storyContextEntryIds: [
          "gone-1",
          "gone-2",
          "gone-3",
          "gone-4",
          "gone-5",
        ],
      }),
    );
    await openSessionAndWait();
    expect(screen.getByTestId("instruction").textContent).toBe("a cat girl");
    expect(screen.getByTestId("story-context").textContent).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "story-toggle-old" }));
    expect(screen.getByTestId("story-context").textContent).toBe("entry-old");
  });

  it("suggestCharacters sends the first filled field as input_text only when there is one", async () => {
    await openSessionAndWait();
    // プロンプト欄が空なら、指示の欄を下書きとして渡す
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
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

    // プロンプト欄があればそちらを優先する
    fireEvent.click(screen.getByRole("button", { name: "edit-prompt" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "suggest" }));
    });
    await waitFor(() =>
      expect(findCalls("/suggest-characters", "POST")).toHaveLength(2),
    );
    expect(lastBody("/suggest-characters", "POST").input_text).toBe(
      "edited prompt",
    );

    fireEvent.click(screen.getByRole("button", { name: "clear-positive" }));
    fireEvent.click(screen.getByRole("button", { name: "clear-instruction" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "suggest" }));
    });
    await waitFor(() =>
      expect(findCalls("/suggest-characters", "POST")).toHaveLength(3),
    );
    expect(lastBody("/suggest-characters", "POST")).not.toHaveProperty(
      "input_text",
    );
  });

  it("manga mode is sent to /expand and /generate only while a V5 model is selected", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    // 日本語モードを選んでいても、漫画モード中はタグ扱いに固定される
    fireEvent.click(screen.getByRole("button", { name: "positive-japanese" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "manga-on" }));
    });
    // V4.5 のままでは漫画モードは効かない
    expect(screen.getByTestId("manga-active").textContent).toBe("off");
    await convertAndWait();
    let expandBody = lastBody("/prompt-expander/expand", "POST");
    expect(expandBody.manga_mode).toBe(false);
    expect(expandBody).not.toHaveProperty("manga");
    expect(expandBody.positive_mode).toBe("japanese");
    expect(
      JSON.parse(screen.getByTestId("positive-origin").textContent ?? "{}")
        .mode,
    ).toBe("japanese");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "manga-on-v5" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("manga-active").textContent).toBe("on"),
    );
    await convertAndWait();
    expandBody = lastBody("/prompt-expander/expand", "POST");
    expect(expandBody.manga_mode).toBe(true);
    expect(expandBody.positive_mode).toBe("tags");
    expect(
      JSON.parse(screen.getByTestId("positive-origin").textContent ?? "{}")
        .mode,
    ).toBe("tags");
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
      fireEvent.click(screen.getByRole("button", { name: "run" }));
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

  it("continues from the V5 usage warning to the precise reference confirm", async () => {
    mockState.imageModel = "nai-diffusion-5-full";
    mockState.anlasUsagePercent = 0;
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    fireEvent.click(screen.getByRole("button", { name: "set-reference" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "reference-on" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("reference-active").textContent).toBe("on"),
    );

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("pending-usage").textContent).toBe("yes"),
    );
    // 上限警告を確定しても、精密参照の Anlas 確認を飛ばさない
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "usage-confirm" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("pending-reference").textContent).toBe("yes"),
    );
    expect(findCalls("/generate", "POST")).toHaveLength(0);
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "reference-confirm" }),
      );
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    const references = lastBody("/generate", "POST").references as Array<
      Record<string, unknown>
    >;
    expect(references[0].kind).toBe("entry");
  });

  it("precise reference is sent only with the toggle on, a supported model and a selected image, and waits for the Anlas confirm", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    // 参照画像だけ選んでもトグルが OFF なら載らない
    fireEvent.click(screen.getByRole("button", { name: "set-reference" }));
    expect(screen.getByTestId("reference-active").textContent).toBe("off");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    expect(lastBody("/generate", "POST")).not.toHaveProperty("references");
    expect(lastBody("/generate", "POST").transparent_background).toBe(false);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "reference-on" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("reference-active").textContent).toBe("on"),
    );
    // 参照付きの生成は Anlas 確認で止まる
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("pending-reference").textContent).toBe("yes"),
    );
    expect(findCalls("/generate", "POST")).toHaveLength(1);
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "reference-confirm" }),
      );
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(2));
    const body = lastBody("/generate", "POST");
    expect(body.references).toEqual([
      {
        kind: "entry",
        entry_id: "entry-ref",
        type: "character",
        include_outfit: false,
        strength: 0.85,
        fidelity: 1,
      },
    ]);
    // i2i 元とは独立
    expect(body.source_kind).toBe("none");
    expect(
      sessionStorage.getItem(PROMPT_EXPANDER_ANLAS_WARN_SUPPRESSED_KEY),
    ).toBe("true");
    expect(screen.getByTestId("pending-reference").textContent).toBe("no");

    // 抑止後は確認なしで直接生成する
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(3));
    expect(screen.getByTestId("pending-reference").textContent).toBe("no");

    // V5 では衣装の参照・衣装トグル・1.0 を超える強度も送る
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "reference-on-v5" }));
    });
    fireEvent.click(
      screen.getByRole("button", { name: "reference-v5-options" }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("reference-active").textContent).toBe("on"),
    );
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(4));
    const v5Ref = (
      lastBody("/generate", "POST").references as Array<Record<string, unknown>>
    )[0];
    expect(v5Ref.type).toBe("costume");
    expect(v5Ref.include_outfit).toBe(true);
    expect(v5Ref.strength).toBe(3);

    // V5 Full の節約モードに切り替えると設定は残るが参照は載らない
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "reference-on-economy" }),
      );
    });
    await waitFor(() =>
      expect(screen.getByTestId("reference-active").textContent).toBe("off"),
    );
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(5));
    expect(lastBody("/generate", "POST")).not.toHaveProperty("references");
  });

  it("multiple references: cost per image, cast from named character references, and cast sent to /expand and /manga-script", async () => {
    mockState.imageModel = "nai-diffusion-5-full";
    sessionStorage.setItem(PROMPT_EXPANDER_ANLAS_WARN_SUPPRESSED_KEY, "true");
    await openSessionAndWait();
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "manga-reference-on-v5" }),
      );
    });
    await waitFor(() =>
      expect(screen.getByTestId("manga-active").textContent).toBe("on"),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "add-character-reference" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "add-upload-reference" }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("reference-count").textContent).toBe("2"),
    );
    expect(screen.getByTestId("reference-cost").textContent).toBe("10");
    expect(
      JSON.parse(screen.getByTestId("reference-cast").textContent ?? ""),
    ).toEqual([
      { name: "サクラ", appearance_tags: "1girl, pink hair" },
      { name: "ユイ", appearance_tags: "1girl, black hair" },
    ]);

    // 生成は 2 枚とも送り、キャラクターはプリセット ID、名前も付ける
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    const references = lastBody("/generate", "POST").references as Array<
      Record<string, unknown>
    >;
    expect(references.map((r) => r.kind)).toEqual(["character", "upload"]);
    expect(references[0]).toMatchObject({
      character_preset_id: "preset-1",
      name: "サクラ",
      appearance_tags: "1girl, pink hair",
    });
    expect(references[1].image).toBe("data:image/png;base64,AAAA");

    // キャラ枠 ON のプロンプト化とネーム下書きにキャストを渡す
    fireEvent.click(screen.getByRole("button", { name: "character-on" }));
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    await convertAndWait();
    expect(lastBody("/prompt-expander/expand", "POST").cast).toHaveLength(2);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "draft-script" }));
    });
    await waitFor(() =>
      expect(findCalls("/prompt-expander/manga-script", "POST")).toHaveLength(
        1,
      ),
    );
    expect(lastBody("/prompt-expander/manga-script", "POST").cast).toHaveLength(
      2,
    );

    // 画風に変えた参照は登場人物にならない
    fireEvent.click(
      screen.getByRole("button", { name: "first-reference-style" }),
    );
    await waitFor(() =>
      expect(
        JSON.parse(screen.getByTestId("reference-cast").textContent ?? ""),
      ).toHaveLength(1),
    );
  });

  it("transparent_background is sent to /expand and /generate, but not while comic mode is active", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "transparent-on" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("transparent-active").textContent).toBe("on"),
    );
    await convertAndWait();
    expect(
      lastBody("/prompt-expander/expand", "POST").transparent_background,
    ).toBe(true);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    expect(lastBody("/generate", "POST").transparent_background).toBe(true);

    // 漫画モード（V5）中はコマ枠を切り抜けないので無効（設定は残る）
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "transparent-on-manga-v5" }),
      );
    });
    await waitFor(() =>
      expect(screen.getByTestId("manga-active").textContent).toBe("on"),
    );
    expect(screen.getByTestId("transparent-active").textContent).toBe("off");
    await convertAndWait();
    const expandBody = lastBody("/prompt-expander/expand", "POST");
    expect(expandBody.manga_mode).toBe(true);
    expect(expandBody.transparent_background).toBe(false);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(2));
    expect(lastBody("/generate", "POST").transparent_background).toBe(false);
  });

  it("restoreEntry restores transparency and reference settings; regenerateEntry re-sends entry references and drops upload ones", async () => {
    // 参照付きの再生成が Anlas 確認で止まらないよう抑止しておく
    sessionStorage.setItem(PROMPT_EXPANDER_ANLAS_WARN_SUPPRESSED_KEY, "true");
    await openSessionAndWait();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "restore-ref" }));
    });
    await waitFor(() => {
      const putCalls = findCalls("/prompt-expander/settings", "PUT");
      expect(putCalls.length).toBeGreaterThan(0);
      const body = JSON.parse(String(putCalls[putCalls.length - 1].init?.body));
      expect(body.transparent_background).toBe(true);
      expect(body.use_precise_reference).toBe(true);
    });
    // 精密参照も画像ごとの設定・名前・外見タグごと戻す（アップロードと削除済みのキャラクターは外す）
    await waitFor(() =>
      expect(screen.getByTestId("reference-count").textContent).toBe("2"),
    );
    expect(
      JSON.parse(screen.getByTestId("reference-detail").textContent ?? ""),
    ).toEqual([
      {
        kind: "entry",
        type: "style",
        strength: 0.5,
        includeOutfit: false,
        name: "",
        appearanceTags: "",
        thumbnailUrl: "/api/prompt-expander/images/entry-ref",
      },
      {
        kind: "character",
        type: "character",
        strength: 0.5,
        includeOutfit: true,
        name: "サクラ",
        // 生成時に使った外見タグを戻す（プリセットの今の値ではなく）
        appearanceTags: "1girl, pink hair",
        thumbnailUrl:
          "/api/game/character-presets/preset-1/images/portrait.png",
      },
    ]);
    // 外した 2 枚（削除済みのキャラクター・アップロード）は通知で知らせる
    await waitFor(() =>
      expect(screen.getByTestId("notifications").textContent).not.toBe(""),
    );
    const notificationsAfterRestore =
      screen.getByTestId("notifications").textContent ?? "";
    // 参照なしのエントリの復元では透過だけ戻し、参照トグルには触れない
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "restore" }));
    });
    await waitFor(() => {
      const putCalls = findCalls("/prompt-expander/settings", "PUT");
      const body = JSON.parse(String(putCalls[putCalls.length - 1].init?.body));
      expect(body.transparent_background).toBe(false);
      expect(body).not.toHaveProperty("use_precise_reference");
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "regenerate-ref" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    const body = lastBody("/generate", "POST");
    expect(body.references).toEqual([
      {
        kind: "entry",
        entry_id: "entry-ref",
        type: "style",
        include_outfit: false,
        strength: 0.5,
        fidelity: 0.75,
      },
    ]);
    expect(body.transparent_background).toBe(true);
    expect(body).not.toHaveProperty("seed");
    // 再現できる参照だけなので、再生成では新しい通知を出さない
    expect(screen.getByTestId("notifications").textContent).toBe(
      notificationsAfterRestore,
    );

    // アップロード参照は保持していないので外し（知らせる）、キャラクター参照は ID で送り直す
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "regenerate-ref-upload" }),
      );
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(2));
    const uploadBody = lastBody("/generate", "POST");
    expect(uploadBody.references).toEqual([
      {
        kind: "character",
        character_preset_id: "preset-1",
        type: "character",
        include_outfit: true,
        strength: 0.5,
        fidelity: 1,
        name: "サクラ",
      },
    ]);
    expect(uploadBody.transparent_background).toBe(false);
    expect(screen.getByTestId("notifications").textContent).not.toBe(
      notificationsAfterRestore,
    );
  });
  it("generation finished after switching sessions stays with the session it started in", async () => {
    let release: () => void = () => {};
    mockState.generateGate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("generating-session").textContent).toBe(
        "sess-1",
      ),
    );
    // 応答を待つ間に別のセッションを開く
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "open-2" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("session").textContent).toBe("sess-2"),
    );
    await act(async () => {
      release();
    });
    await waitFor(() =>
      expect(screen.getByTestId("outcome").textContent).not.toBe("none"),
    );
    // いま開いている sess-2 の履歴には入らず、開始元の sess-1 の件数だけ増える
    expect(screen.getByTestId("entries").textContent).toBe("");
    expect(screen.getByTestId("session-counts").textContent).toContain(
      "sess-1:2",
    );
    expect(JSON.parse(screen.getByTestId("outcome").textContent ?? "")).toEqual(
      { status: "success", sessionId: "sess-1", entryId: "entry-new" },
    );
    expect(screen.getByTestId("generating-session").textContent).toBe("none");
  });

  it("records a failed generation as an error outcome", async () => {
    mockState.generateErrorCode = "image_failed";
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("outcome").textContent).not.toBe("none"),
    );
    const outcome = JSON.parse(screen.getByTestId("outcome").textContent ?? "");
    expect(outcome.status).toBe("error");
    expect(outcome.sessionId).toBe("sess-1");
    expect(outcome.message).toContain("image_failed");
  });

  it("restoreEntry over a draft can be undone, including the settings it changed", async () => {
    await openSessionAndWait();
    // 欄が空なら控えない
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "restore" }));
    });
    expect(screen.getByTestId("restore-undo").textContent).toBe("none");

    fireEvent.click(screen.getByRole("button", { name: "set-instruction-2" }));
    fireEvent.click(screen.getByRole("button", { name: "set-script" }));
    fireEvent.click(screen.getByRole("button", { name: "set-positive" }));
    fireEvent.click(screen.getByRole("button", { name: "input-direct" }));
    const putsBefore = findCalls("/prompt-expander/settings", "PUT").length;
    const modelBefore = screen.getByTestId("image-model").textContent;
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "restore" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("restore-undo").textContent).not.toBe("none"),
    );
    expect(screen.getByTestId("positive").textContent).not.toBe("a cat girl");
    await waitFor(() =>
      expect(
        findCalls("/prompt-expander/settings", "PUT").length,
      ).toBeGreaterThan(putsBefore),
    );
    const restorePatch = lastBody("/prompt-expander/settings", "PUT");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "undo-restore" }));
    });
    // 3 つの欄と入れ方の切り替えも戻る
    expect(screen.getByTestId("instruction").textContent).toBe("a dog girl");
    expect(screen.getByTestId("script").textContent).toBe("①鏡を見る「え」");
    expect(screen.getByTestId("positive").textContent).toBe("a cat girl");
    expect(screen.getByTestId("input-mode").textContent).toBe("direct");
    expect(screen.getByTestId("restore-undo").textContent).toBe("none");
    // 復元で変えた設定と同じキーを、復元前の値で送り直す
    await waitFor(() => {
      const undoPatch = lastBody("/prompt-expander/settings", "PUT");
      expect(Object.keys(undoPatch).sort()).toEqual(
        Object.keys(restorePatch).sort(),
      );
      expect(undoPatch.image_model).toBe(modelBefore);
    });
  });

  it("keeps the prompt when the negative field is converted, and keeps a card when re-conversion fails", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    fireEvent.click(screen.getByRole("button", { name: "set-negative" }));
    await convertAndWait();

    // ネガティブ欄をプロンプト化しても、プロンプト欄はそのまま
    await clickAndWaitPending("expand-negative");
    expect(screen.getByTestId("positive").textContent).toBe(
      "expanded: a cat girl",
    );

    // 再変換が失敗しても、今のプロンプトとカードは消えない
    mockState.expandErrorCode = "llm_failed";
    await convertAndWait();
    await convertAndWait("expand-negative");
    expect(screen.getByTestId("positive").textContent).toBe(
      "expanded: a cat girl",
    );
    expect(screen.getByTestId("pending-expansion").textContent).not.toBe(
      "none",
    );
  });

  it("keeps a separate draft for each session and restores it after a reload", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    fireEvent.click(screen.getByRole("button", { name: "set-script" }));
    fireEvent.click(screen.getByRole("button", { name: "edit-prompt" }));
    fireEvent.click(screen.getByRole("button", { name: "set-negative" }));

    // 別のセッションを開くと、そのセッションの書きかけ（ここでは空）に入れ替わる
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "open-2" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("session").textContent).toBe("sess-2"),
    );
    await waitFor(() =>
      expect(screen.getByTestId("positive").textContent).toBe(""),
    );
    expect(screen.getByTestId("instruction").textContent).toBe("");
    expect(screen.getByTestId("script").textContent).toBe("");
    expect(screen.getByTestId("negative").textContent).toBe("");

    // 元のセッションへ戻ると続きが戻る
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "open" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("positive").textContent).toBe("edited prompt"),
    );
    expect(screen.getByTestId("instruction").textContent).toBe("a cat girl");
    expect(screen.getByTestId("script").textContent).toBe("①鏡を見る「え」");
    expect(screen.getByTestId("negative").textContent).toBe("blurry");

    // 再読み込み（作り直し）しても、同じタブなら残る
    cleanup();
    await openSessionAndWait();
    await waitFor(() =>
      expect(screen.getByTestId("positive").textContent).toBe("edited prompt"),
    );
    expect(screen.getByTestId("instruction").textContent).toBe("a cat girl");
    expect(screen.getByTestId("script").textContent).toBe("①鏡を見る「え」");
  });

  it("reads a draft saved before the fields were split", async () => {
    // 拡張結果を反映済みの書きかけ: 旧プロンプト欄はプロンプトへ、元の指示は指示欄へ
    sessionStorage.setItem(
      "prompt_expander_draft:sess-1",
      JSON.stringify({
        positiveText: "1girl, cat ears",
        negativeText: "lowres",
        characterSlots: [],
        positiveOrigin: { mode: "tags", instruction: "猫耳の少女" },
        negativeOrigin: null,
        pendingExpansions: {
          positive: null,
          negative: { target: "negative", mode: "tags", negativePrompt: "bad" },
        },
        latestExpansionTarget: "negative",
        scriptDraftBackup: null,
      }),
    );
    await openSessionAndWait();
    await waitFor(() =>
      expect(screen.getByTestId("positive").textContent).toBe(
        "1girl, cat ears",
      ),
    );
    expect(screen.getByTestId("instruction").textContent).toBe("猫耳の少女");
    expect(screen.getByTestId("negative").textContent).toBe("lowres");
    expect(
      JSON.parse(screen.getByTestId("pending-expansion").textContent ?? "{}"),
    ).toEqual({ mode: "tags", negativePrompt: "bad" });

    // ネームを下書きした後の書きかけ: 旧プロンプト欄はネーム欄へ、控えのあらすじは指示欄へ
    cleanup();
    sessionStorage.setItem(
      "prompt_expander_draft:sess-1",
      JSON.stringify({
        positiveText: "①鏡を見る「え」",
        negativeText: "",
        characterSlots: [],
        positiveOrigin: null,
        negativeOrigin: null,
        pendingExpansions: { positive: null, negative: null },
        latestExpansionTarget: null,
        scriptDraftBackup: { source: "あらすじ", script: "①鏡を見る「え」" },
      }),
    );
    await openSessionAndWait();
    await waitFor(() =>
      expect(screen.getByTestId("script").textContent).toBe("①鏡を見る「え」"),
    );
    expect(screen.getByTestId("instruction").textContent).toBe("あらすじ");
    expect(screen.getByTestId("positive").textContent).toBe("");
  });

  it("a storyboard requested in one session lands only in that session's draft", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    let release: () => void = () => {};
    mockState.llmGate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "draft-script" }));
    });

    // 応答の前に別のセッションへ移る
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "open-2" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("session").textContent).toBe("sess-2"),
    );
    await act(async () => {
      release();
    });
    await waitFor(() =>
      expect(screen.getByTestId("drafting").textContent).toBe("no"),
    );
    // 移った先の欄は書き換えない
    expect(screen.getByTestId("script").textContent).toBe("");
    expect(screen.getByTestId("instruction").textContent).toBe("");

    // 依頼したセッションへ戻ると、あらすじとネームが入っている
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "open" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("script").textContent).toContain("①a cat girl"),
    );
    expect(screen.getByTestId("instruction").textContent).toBe("a cat girl");
  });

  it("a conversion requested in one session lands only in that session's draft", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    let release: () => void = () => {};
    mockState.llmGate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "expand-positive" }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "open-2" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("session").textContent).toBe("sess-2"),
    );
    await act(async () => {
      release();
    });
    await waitFor(() =>
      expect(screen.getByTestId("expanding").textContent).toBe("none"),
    );
    expect(screen.getByTestId("positive").textContent).toBe("");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "open" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("positive").textContent).toBe(
        "expanded: a cat girl",
      ),
    );
    expect(
      JSON.parse(screen.getByTestId("positive-origin").textContent ?? "{}")
        .instruction,
    ).toBe("a cat girl");
  });

  it("a conversion that returns after restoreEntry does not overwrite the restored fields", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    let release: () => void = () => {};
    mockState.llmGate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "expand-positive" }));
    });
    expect(screen.getByTestId("expanding").textContent).toBe("positive");

    // 応答の前に別の履歴を復元すると、変換中の表示はその場で止まる
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "restore" }));
    });
    expect(screen.getByTestId("expanding").textContent).toBe("none");
    await act(async () => {
      release();
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    // 遅れて届いた結果は、復元した欄を上書きしない
    expect(screen.getByTestId("instruction").textContent).toBe(
      "old instruction",
    );
    expect(screen.getByTestId("positive").textContent).toBe(
      "1girl, old prompt",
    );
    expect(
      JSON.parse(screen.getByTestId("positive-origin").textContent ?? "{}")
        .instruction,
    ).toBe("old instruction");
    expect(screen.getByTestId("expanding").textContent).toBe("none");

    // そのまま生成すると、復元した作品の内容を送る
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "run" }));
    });
    await waitFor(() => expect(findCalls("/generate", "POST")).toHaveLength(1));
    expect(lastBody("/generate", "POST")).toMatchObject({
      prompt: "1girl, old prompt",
      instruction: "old instruction",
    });
  });

  it("a storyboard draft that returns after restoreEntry does not overwrite the restored storyboard", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "manga-on-v5" }));
    await waitFor(() =>
      expect(screen.getByTestId("manga-active").textContent).toBe("on"),
    );
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    let release: () => void = () => {};
    mockState.llmGate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "draft-script" }));
    });
    expect(screen.getByTestId("drafting").textContent).toBe("yes");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "restore-script" }));
    });
    expect(screen.getByTestId("drafting").textContent).toBe("no");
    await act(async () => {
      release();
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(screen.getByTestId("script").textContent).toBe("①鏡を見る「え」");
    expect(screen.getByTestId("instruction").textContent).toBe(
      "朝起きたら女の子になっていた",
    );
    expect(screen.getByTestId("script-undo").textContent).toBe("none");
  });

  it("an error from a conversion discarded by undoRestore is not shown", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    // 書きかけの上に復元しておき、変換の途中で復元を取り消す
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "restore" }));
    });
    let release: () => void = () => {};
    mockState.llmGate = new Promise<void>((resolve) => {
      release = resolve;
    });
    mockState.expandErrorCode = "llm_failed";
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "expand-positive" }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "undo-restore" }));
    });
    expect(screen.getByTestId("expanding").textContent).toBe("none");
    expect(screen.getByTestId("instruction").textContent).toBe("a cat girl");
    await act(async () => {
      release();
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(screen.getByTestId("expansion-error").textContent).toBe("none");
    expect(screen.getByTestId("instruction").textContent).toBe("a cat girl");
    expect(screen.getByTestId("positive").textContent).toBe("");
  });

  it("a session load that returns late does not replace the session opened after it", async () => {
    renderProvider();
    await waitFor(() =>
      expect(screen.getByTestId("settings-loaded").textContent).toBe("yes"),
    );
    let release: () => void = () => {};
    mockState.sessionGates["sess-1"] = new Promise<void>((resolve) => {
      release = resolve;
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "open" }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "open-2" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("session").textContent).toBe("sess-2"),
    );
    await act(async () => {
      release();
    });
    await waitFor(() =>
      expect(findCalls("/sessions/sess-1", "GET")).toHaveLength(1),
    );
    expect(screen.getByTestId("session").textContent).toBe("sess-2");
    expect(screen.getByTestId("entries").textContent).toBe("");
  });

  it("keeps hand edits on the negative conversion card in the session draft across a reload", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-negative" }));
    await clickAndWaitPending("expand-negative");
    fireEvent.click(screen.getByRole("button", { name: "edit-card" }));
    expect(screen.getByTestId("pending-negative-prompt").textContent).toBe(
      "hand edited",
    );

    cleanup();
    await openSessionAndWait();
    await waitFor(() =>
      expect(screen.getByTestId("pending-negative-prompt").textContent).toBe(
        "hand edited",
      ),
    );
  });

  it("undoing a restore also brings back the storyboard and its undo", async () => {
    await openSessionAndWait();
    fireEvent.click(screen.getByRole("button", { name: "set-instruction" }));
    fireEvent.click(screen.getByRole("button", { name: "set-script" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "draft-script" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("script-undo").textContent).toBe(
        "①鏡を見る「え」",
      ),
    );
    const script = screen.getByTestId("script").textContent;

    fireEvent.click(screen.getByRole("button", { name: "restore" }));
    expect(screen.getByTestId("script").textContent).toBe("");
    expect(screen.getByTestId("script-undo").textContent).toBe("none");

    fireEvent.click(screen.getByRole("button", { name: "undo-restore" }));
    expect(screen.getByTestId("instruction").textContent).toBe("a cat girl");
    expect(screen.getByTestId("script").textContent).toBe(script);
    expect(screen.getByTestId("script-undo").textContent).toBe(
      "①鏡を見る「え」",
    );
  });

  it("renameSession tells whether the name was saved", async () => {
    await openSessionAndWait();
    mockState.renameErrorCode = "unavailable";
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "rename" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("rename-result").textContent).toBe("failed"),
    );
    expect(screen.getByTestId("session-title").textContent).toBe(
      "Test session",
    );

    mockState.renameErrorCode = null;
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "rename" }));
    });
    await waitFor(() =>
      expect(screen.getByTestId("rename-result").textContent).toBe("saved"),
    );
    expect(screen.getByTestId("session-title").textContent).toBe("New name");
  });
});
