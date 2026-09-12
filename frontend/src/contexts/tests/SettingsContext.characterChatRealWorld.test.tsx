import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsProvider, useSettings } from "../SettingsContext";

const fetchMock = vi.fn(
  async (_input: RequestInfo | URL, _init?: RequestInit) =>
    ({ ok: false }) as Response,
);

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  fetchMock.mockClear();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function FlagProbe() {
  const {
    state,
    setCharacterChatWebSearchEnabled,
    setCharacterChatWeatherEnabled,
  } = useSettings();
  return (
    <>
      <div data-testid="web-search">
        {state.characterChatWebSearchEnabled ? "on" : "off"}
      </div>
      <div data-testid="weather">
        {state.characterChatWeatherEnabled ? "on" : "off"}
      </div>
      <button
        type="button"
        onClick={() => setCharacterChatWebSearchEnabled(true)}
      >
        enable-web-search
      </button>
      <button
        type="button"
        onClick={() => setCharacterChatWebSearchEnabled(false)}
      >
        disable-web-search
      </button>
      <button
        type="button"
        onClick={() => setCharacterChatWeatherEnabled(true)}
      >
        enable-weather
      </button>
    </>
  );
}

function readSaved(): Record<string, unknown> {
  return JSON.parse(localStorage.getItem("app_settings") ?? "{}");
}

describe("SettingsContext character chat web search / weather", () => {
  it("defaults both flags to false", () => {
    render(
      <SettingsProvider>
        <FlagProbe />
      </SettingsProvider>,
    );
    expect(screen.getByTestId("web-search").textContent).toBe("off");
    expect(screen.getByTestId("weather").textContent).toBe("off");
  });

  it("persists both flags to localStorage app_settings only", async () => {
    render(
      <SettingsProvider>
        <FlagProbe />
      </SettingsProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "enable-web-search" }));
    expect(screen.getByTestId("web-search").textContent).toBe("on");
    await waitFor(() => {
      expect(readSaved().characterChatWebSearchEnabled).toBe(true);
      expect(readSaved().characterChatWeatherEnabled).toBe(false);
    });

    fireEvent.click(screen.getByRole("button", { name: "enable-weather" }));
    fireEvent.click(screen.getByRole("button", { name: "disable-web-search" }));
    await waitFor(() => {
      expect(readSaved().characterChatWebSearchEnabled).toBe(false);
      expect(readSaved().characterChatWeatherEnabled).toBe(true);
    });

    // ユーザー設定 API(DB)には送らない
    const putBodies = fetchMock.mock.calls
      .filter(([, init]) => init?.method === "PUT")
      .map(([, init]) => String(init?.body));
    expect(putBodies.some((body) => body.includes("web_search"))).toBe(false);
    expect(putBodies.some((body) => body.includes("weather"))).toBe(false);
  });

  it("restores both flags from localStorage on load", async () => {
    localStorage.setItem(
      "app_settings",
      JSON.stringify({
        characterChatWebSearchEnabled: true,
        characterChatWeatherEnabled: true,
      }),
    );
    render(
      <SettingsProvider>
        <FlagProbe />
      </SettingsProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("web-search").textContent).toBe("on");
      expect(screen.getByTestId("weather").textContent).toBe("on");
    });
  });
});
