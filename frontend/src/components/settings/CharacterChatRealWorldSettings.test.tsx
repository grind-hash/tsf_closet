import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "../../i18n";
import { SettingsProvider } from "../../contexts/SettingsContext";
import CharacterChatRealWorldSettings from "./CharacterChatRealWorldSettings";

const WEB_SEARCH_NOTE = /TAVILY_API_KEY が設定されていない/;
const WEATHER_NOTE = /WEATHER_LOCATION（例: Tokyo）が設定されていない/;

/** GET /api/settings/user の応答。null なら失敗させる */
let userSettings: Record<string, unknown> | null = null;

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  } as unknown as Response;
}

const fetchMock = vi.fn(
  async (input: RequestInfo | URL, init?: RequestInit) => {
    if (
      String(input) === "/api/settings/user" &&
      !init?.method &&
      userSettings
    ) {
      return jsonResponse(200, userSettings);
    }
    return jsonResponse(500, null);
  },
);

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  userSettings = null;
  fetchMock.mockClear();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderSettings() {
  return render(
    <SettingsProvider>
      <CharacterChatRealWorldSettings />
    </SettingsProvider>,
  );
}

/** 設定状況の取得が終わるまで待つ */
async function settle() {
  await waitFor(() => {
    expect(
      fetchMock.mock.calls.some(([url]) => url === "/api/settings/user"),
    ).toBe(true);
  });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

function webSearchSwitch(): HTMLInputElement {
  return screen.getByRole("checkbox", {
    name: /セレナがWeb検索で調べる/,
  }) as HTMLInputElement;
}

function weatherSwitch(): HTMLInputElement {
  return screen.getByRole("checkbox", {
    name: /セレナが天気を調べる/,
  }) as HTMLInputElement;
}

describe("CharacterChatRealWorldSettings", () => {
  it("explains only the web search when TAVILY_API_KEY is missing", async () => {
    userSettings = {
      nsfw_mode: false,
      difficulty: "normal",
      web_search_configured: false,
      weather_configured: true,
    };
    renderSettings();
    const note = await screen.findByRole("note");
    expect(note.textContent).toMatch(WEB_SEARCH_NOTE);
    expect(screen.getAllByRole("note")).toHaveLength(1);
    expect(screen.queryByText(WEATHER_NOTE)).toBeNull();
  });

  it("explains only the weather when WEATHER_LOCATION is missing", async () => {
    userSettings = {
      nsfw_mode: false,
      difficulty: "normal",
      web_search_configured: true,
      weather_configured: false,
    };
    renderSettings();
    const note = await screen.findByRole("note");
    expect(note.textContent).toMatch(WEATHER_NOTE);
    expect(screen.getAllByRole("note")).toHaveLength(1);
    expect(screen.queryByText(WEB_SEARCH_NOTE)).toBeNull();
  });

  it("keeps both switches operable while unconfigured and toggles the settings", async () => {
    userSettings = {
      nsfw_mode: false,
      difficulty: "normal",
      web_search_configured: false,
      weather_configured: false,
    };
    renderSettings();
    expect(await screen.findAllByRole("note")).toHaveLength(2);

    expect(webSearchSwitch().disabled).toBe(false);
    expect(weatherSwitch().disabled).toBe(false);
    expect(webSearchSwitch().checked).toBe(false);
    expect(weatherSwitch().checked).toBe(false);

    fireEvent.click(webSearchSwitch());
    fireEvent.click(screen.getByRole("button", { name: "同意して有効にする" }));
    expect(webSearchSwitch().checked).toBe(true);
    expect(weatherSwitch().checked).toBe(false);

    fireEvent.click(weatherSwitch());
    expect(weatherSwitch().checked).toBe(true);
    await waitFor(() => {
      const saved = JSON.parse(localStorage.getItem("app_settings") ?? "{}");
      expect(saved.characterChatWebSearchEnabled).toBe(true);
      expect(saved.characterChatWeatherEnabled).toBe(true);
    });

    fireEvent.click(webSearchSwitch());
    expect(webSearchSwitch().checked).toBe(false);
    expect(weatherSwitch().checked).toBe(true);
  });

  it("shows no note when the configuration cannot be fetched", async () => {
    renderSettings();
    await settle();
    expect(screen.queryByRole("note")).toBeNull();
    expect(webSearchSwitch().disabled).toBe(false);
    expect(weatherSwitch().disabled).toBe(false);
  });

  it("shows no note when the server does not report the configuration", async () => {
    userSettings = { nsfw_mode: false, difficulty: "normal" };
    renderSettings();
    await settle();
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("asks for agreement to Tavily's terms before turning web search on", async () => {
    userSettings = {
      nsfw_mode: false,
      difficulty: "normal",
      web_search_configured: true,
      weather_configured: true,
    };
    renderSettings();
    await settle();

    fireEvent.click(webSearchSwitch());
    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).toMatch(
      /外部検索サービス「Tavily」を利用します/,
    );
    expect(
      screen.getAllByRole("listitem").map((item) => item.textContent),
    ).toEqual([
      "ポルノまたは露骨な性的コンテンツ",
      "未成年者に関する不適切なコンテンツ",
      "違法行為に関するコンテンツ",
      "その他TavilyのAcceptable Use Policyで禁止されているコンテンツ",
    ]);
    expect(dialog.textContent).toMatch(
      /上記およびTavilyの利用条件に同意したものとします/,
    );
    const link = screen.getByRole("link", {
      name: /TavilyのAcceptable Use Policyを読む/,
    });
    expect(link.getAttribute("href")).toBe(
      "https://www.tavily.com/acceptable-use-policy",
    );
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    // 同意するまでは OFF のまま
    expect(webSearchSwitch().checked).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "キャンセル" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(webSearchSwitch().checked).toBe(false);

    fireEvent.click(webSearchSwitch());
    fireEvent.click(screen.getByRole("button", { name: "同意して有効にする" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(webSearchSwitch().checked).toBe(true);

    // OFF にするときは確認しない
    fireEvent.click(webSearchSwitch());
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(webSearchSwitch().checked).toBe(false);
  });

  it("does not ask for agreement when turning the weather on", async () => {
    renderSettings();
    await settle();
    fireEvent.click(weatherSwitch());
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(weatherSwitch().checked).toBe(true);
  });
});
