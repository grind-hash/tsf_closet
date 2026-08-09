import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { SettingsProvider, useSettings } from "../SettingsContext";

afterEach(() => {
  cleanup();
});

function InpaintProbe() {
  const { state, setInpaintMask, toggleInpaint } = useSettings();

  return (
    <>
      <div data-testid="mask-id">
        {state.inpaintMask.selectedMaskId ?? "none"}
      </div>
      <button type="button" onClick={() => toggleInpaint()}>
        toggle
      </button>
      <button
        type="button"
        onClick={() => setInpaintMask("data:image/png;base64,abc", "mask-1")}
      >
        set-mask
      </button>
    </>
  );
}

function ExperimentalEndingProbe() {
  const { state, setExperimentalEndingEnabled } = useSettings();

  return (
    <>
      <div data-testid="experimental-ending-enabled">
        {state.experimentalEndingEnabled ? "on" : "off"}
      </div>
      <button type="button" onClick={() => setExperimentalEndingEnabled(true)}>
        enable-ending
      </button>
    </>
  );
}

function PlayMemoryPreferenceProbe() {
  const { state, setPlayMemorySystemEnabled, setPlayMemoryUserEnabled } =
    useSettings();

  return (
    <>
      <div data-testid="play-memory-system-enabled">
        {state.playMemorySystemEnabled ? "on" : "off"}
      </div>
      <div data-testid="play-memory-user-enabled">
        {state.playMemoryUserEnabled ? "on" : "off"}
      </div>
      <button type="button" onClick={() => setPlayMemorySystemEnabled(false)}>
        disable-system-memory
      </button>
      <button type="button" onClick={() => setPlayMemoryUserEnabled(false)}>
        disable-user-memory
      </button>
    </>
  );
}

describe("SettingsContext inpaint state", () => {
  it("clears mask state when inpaint is toggled off", () => {
    render(
      <SettingsProvider>
        <InpaintProbe />
      </SettingsProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "toggle" }));
    fireEvent.click(screen.getByRole("button", { name: "set-mask" }));
    expect(screen.getByTestId("mask-id").textContent).toBe("mask-1");

    fireEvent.click(screen.getByRole("button", { name: "toggle" }));
    expect(screen.getByTestId("mask-id").textContent).toBe("none");
  });

  it("keeps experimental ending disabled by default and enables by toggle", () => {
    render(
      <SettingsProvider>
        <ExperimentalEndingProbe />
      </SettingsProvider>,
    );

    expect(screen.getByTestId("experimental-ending-enabled").textContent).toBe(
      "off",
    );
    fireEvent.click(screen.getByRole("button", { name: "enable-ending" }));
    expect(screen.getByTestId("experimental-ending-enabled").textContent).toBe(
      "on",
    );
  });
});

describe("SettingsContext play memory preferences", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("defaults both preferences to enabled for legacy settings", () => {
    localStorage.setItem(
      "app_settings",
      JSON.stringify({ playMemoryEnabled: true }),
    );

    render(
      <SettingsProvider>
        <PlayMemoryPreferenceProbe />
      </SettingsProvider>,
    );

    expect(screen.getByTestId("play-memory-system-enabled").textContent).toBe(
      "on",
    );
    expect(screen.getByTestId("play-memory-user-enabled").textContent).toBe(
      "on",
    );
  });

  it("persists only the enabled preferences in app settings", async () => {
    const { unmount } = render(
      <SettingsProvider>
        <PlayMemoryPreferenceProbe />
      </SettingsProvider>,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "disable-system-memory" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "disable-user-memory" }),
    );

    await waitFor(() => {
      const saved = JSON.parse(localStorage.getItem("app_settings") ?? "{}");
      expect(saved.playMemorySystemEnabled).toBe(false);
      expect(saved.playMemoryUserEnabled).toBe(false);
      expect(saved).not.toHaveProperty("systemText");
      expect(saved).not.toHaveProperty("userText");
    });

    unmount();
    render(
      <SettingsProvider>
        <PlayMemoryPreferenceProbe />
      </SettingsProvider>,
    );

    expect(screen.getByTestId("play-memory-system-enabled").textContent).toBe(
      "off",
    );
    expect(screen.getByTestId("play-memory-user-enabled").textContent).toBe(
      "off",
    );
  });
});
