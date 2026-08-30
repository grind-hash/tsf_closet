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
  const { state, setExperimentalPromptExpanderEnabled } = useSettings();
  return (
    <>
      <div data-testid="flag">
        {state.experimentalPromptExpanderEnabled ? "on" : "off"}
      </div>
      <button
        type="button"
        onClick={() => setExperimentalPromptExpanderEnabled(true)}
      >
        enable
      </button>
      <button
        type="button"
        onClick={() => setExperimentalPromptExpanderEnabled(false)}
      >
        disable
      </button>
    </>
  );
}

describe("SettingsContext experimentalPromptExpanderEnabled", () => {
  it("defaults to false", () => {
    render(
      <SettingsProvider>
        <FlagProbe />
      </SettingsProvider>,
    );
    expect(screen.getByTestId("flag").textContent).toBe("off");
  });

  it("persists the flag to localStorage app_settings", async () => {
    render(
      <SettingsProvider>
        <FlagProbe />
      </SettingsProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "enable" }));
    expect(screen.getByTestId("flag").textContent).toBe("on");

    await waitFor(() => {
      const saved = JSON.parse(localStorage.getItem("app_settings") ?? "{}");
      expect(saved.experimentalPromptExpanderEnabled).toBe(true);
    });

    fireEvent.click(screen.getByRole("button", { name: "disable" }));
    await waitFor(() => {
      const saved = JSON.parse(localStorage.getItem("app_settings") ?? "{}");
      expect(saved.experimentalPromptExpanderEnabled).toBe(false);
    });
  });

  it("restores the flag from localStorage on load", async () => {
    localStorage.setItem(
      "app_settings",
      JSON.stringify({ experimentalPromptExpanderEnabled: true }),
    );
    render(
      <SettingsProvider>
        <FlagProbe />
      </SettingsProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("flag").textContent).toBe("on");
    });
  });
});
