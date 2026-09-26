import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import "../../i18n";
import { SettingsProvider } from "../../contexts/SettingsContext";
import SpeechSynthesisSettings from "./SpeechSynthesisSettings";

const SPEAKER_UUID = "11111111-2222-3333-4444-555555555555";

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    statusText: "",
    json: async () => body,
  } as unknown as Response;
}

const requestedUrls: string[] = [];

const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
  const url = String(input);
  requestedUrls.push(url);

  if (url === "/api/settings/user") {
    return jsonResponse({
      tts_enabled: true,
      tts_speaker_id: SPEAKER_UUID,
      tts_style_id: "1",
    });
  }
  if (url === "/api/aivisspeech/defaults") {
    return jsonResponse({
      engine_download_url: "https://example.invalid/engine.zip",
      model_download_url: "https://example.invalid/model.aivmx",
    });
  }
  if (url === "/api/aivisspeech/status") {
    return jsonResponse({
      process: "running",
      pid: 1234,
      engine_http: "ok",
      engine_base_url: "http://127.0.0.1:10101",
      engine_port: 10101,
      default_engine_port: 10101,
      engine_version: "1.0.0",
      engine_brand: "AivisSpeech",
      aivis_engine_brand: "AivisSpeech",
      default_engine_download_url: "https://example.invalid/engine.zip",
      default_model_url: "https://example.invalid/model.aivmx",
      default_model_dir: "C:/models",
      platform: "windows",
    });
  }
  if (url === "/api/aivisspeech/speakers") {
    return jsonResponse([
      {
        name: "サクラ",
        speaker_uuid: SPEAKER_UUID,
        styles: [{ id: 1, name: "ノーマル" }],
      },
    ]);
  }
  return jsonResponse({});
});

function countRequests(url: string): number {
  return requestedUrls.filter((requested) => requested === url).length;
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  requestedUrls.length = 0;
  fetchMock.mockClear();
  vi.stubGlobal("fetch", fetchMock);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  cleanup();
  vi.unstubAllGlobals();
});

it("状態ポーリングのたびにスピーカー一覧を取り直さない", async () => {
  await act(async () => {
    render(
      <SettingsProvider>
        <SpeechSynthesisSettings />
      </SettingsProvider>,
    );
    await vi.advanceTimersByTimeAsync(0);
  });

  expect(countRequests("/api/aivisspeech/speakers")).toBe(1);

  // 状態ポーリングは 5 秒間隔。3 回分進めても一覧は取り直さない
  await act(async () => {
    await vi.advanceTimersByTimeAsync(16000);
  });

  expect(countRequests("/api/aivisspeech/status")).toBeGreaterThanOrEqual(3);
  expect(countRequests("/api/aivisspeech/speakers")).toBe(1);
});
