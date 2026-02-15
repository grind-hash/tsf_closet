import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SettingsProvider, useSettings } from "../SettingsContext";

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
      <button
        type="button"
        onClick={() => setExperimentalEndingEnabled(true)}
      >
        enable-ending
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
