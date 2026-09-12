// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  type CharacterChatStreamEvent,
  characterChatImageUrl,
  createCharacterChatThread,
  fetchCharacterChatThreads,
  streamCharacterChatMessage,
} from "./characterChat";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  } as unknown as Response;
}

function sseResponse(text: string): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      // chunk 境界がイベント境界と一致しなくても組み立てられることを確かめる
      const mid = Math.floor(text.length / 2);
      controller.enqueue(encoder.encode(text.slice(0, mid)));
      controller.enqueue(encoder.encode(text.slice(mid)));
      controller.close();
    },
  });
  return { ok: true, status: 200, statusText: "", body } as unknown as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("characterChatImageUrl", () => {
  it("prefixes API base for relative urls and keeps absolute ones", () => {
    expect(characterChatImageUrl("/character-chat/images/t1/a.png")).toBe(
      "/api/character-chat/images/t1/a.png",
    );
    expect(characterChatImageUrl("/api/character-chat/images/t1/a.png")).toBe(
      "/api/character-chat/images/t1/a.png",
    );
    expect(characterChatImageUrl("https://x/y.png")).toBe("https://x/y.png");
    expect(characterChatImageUrl(null)).toBeNull();
  });
});

describe("fetchCharacterChatThreads / createCharacterChatThread", () => {
  it("normalizes portrait urls in the list", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        jsonResponse(200, {
          threads: [
            { id: "t1", portrait_url: "/character-chat/images/t1/serena.png" },
            { id: "t2", portrait_url: null },
          ],
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const list = await fetchCharacterChatThreads();
    expect(list.threads.map((t) => t.portrait_url)).toEqual([
      "/api/character-chat/images/t1/serena.png",
      null,
    ]);
    // 未指定の enable_prompt_preview は false 扱い
    expect(list.enablePromptPreview).toBe(false);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/character-chat/threads");
  });

  it("posts the source ids as JSON", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        jsonResponse(201, { id: "t3", portrait_url: null }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await createCharacterChatThread({
      source_session_id: "s1",
      source_history_id: "h1",
    });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/character-chat/threads");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      source_session_id: "s1",
      source_history_id: "h1",
    });
  });
});

describe("streamCharacterChatMessage", () => {
  it("parses named SSE events and resolves portrait urls", async () => {
    const done = {
      user_message: { id: "u1", role: "user", content: "やあ", meta: {} },
      character_message: {
        id: "c1",
        role: "character",
        content: "こんにちは",
        meta: {},
      },
      thread: { id: "t1", message_count: 2, updated_at: null },
    };
    const text = [
      'event: status\ndata: {"phase":"plan"}\n\n',
      'event: chat_chunk\ndata: {"chunk":"こんに"}\n\n',
      'event: chat_chunk\ndata: {"chunk":"ちは"}\n\n',
      `event: chat_done\ndata: ${JSON.stringify(done)}\n\n`,
      'event: portrait_image\ndata: {"image_url":"/character-chat/images/t1/portrait-1.png","appearance":{"identity_tags":"1girl","clothing_tags":"red dress","description":"","portrait_kind":"standing","source":{}}}\n\n',
      'event: cost\ndata: {"cost_usd":0.002}\n\n',
      "event: complete\ndata: {}\n\n",
    ].join("");
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        sseResponse(text),
    );
    vi.stubGlobal("fetch", fetchMock);
    const events: CharacterChatStreamEvent[] = [];
    await streamCharacterChatMessage(
      "t1",
      { content: "やあ", use_web_search: true, use_weather: false },
      (event) => events.push(event),
    );
    expect(events.map((event) => event.type)).toEqual([
      "status",
      "chat_chunk",
      "chat_chunk",
      "chat_done",
      "portrait_image",
      "cost",
      "complete",
    ]);
    const portrait = events[4];
    if (portrait.type !== "portrait_image") throw new Error("unexpected");
    expect(portrait.data.image_url).toBe(
      "/api/character-chat/images/t1/portrait-1.png",
    );
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/character-chat/threads/t1/messages/stream");
    expect(JSON.parse(String(init.body))).toEqual({
      content: "やあ",
      use_web_search: true,
      use_weather: false,
    });
  });

  it("sends the play proposal request flag and passes the propose phase through", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        sseResponse(
          'event: status\ndata: {"phase":"propose"}\n\nevent: complete\ndata: {}\n\n',
        ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const events: CharacterChatStreamEvent[] = [];
    await streamCharacterChatMessage(
      "t1",
      { content: "おすすめのプレイを教えて", request_play_proposal: true },
      (event) => events.push(event),
    );
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      content: "おすすめのプレイを教えて",
      request_play_proposal: true,
    });
    expect(events[0]).toEqual({ type: "status", data: { phase: "propose" } });
  });

  it("throws an ApiError on a non-2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(404, {
          detail: { code: "thread_not_found", message: "missing" },
        }),
      ),
    );
    await expect(
      streamCharacterChatMessage("nope", { content: "やあ" }, () => {}),
    ).rejects.toMatchObject({ code: "thread_not_found" });
  });
});
