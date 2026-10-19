import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SettingsChoice from "./SettingsChoice";
import { SettingsViewContext, type SettingsViewState } from "./SettingsView";

afterEach(cleanup);

const OPTIONS = [
  { id: "easy", label: "Easy", description: "Gentle effects" },
  { id: "hard", label: "Hard", description: "Intense effects" },
] as const;

function renderChoice(mode: SettingsViewState["mode"], onChange = vi.fn()) {
  render(
    <SettingsViewContext.Provider
      value={{
        mode,
        activeCategory: "game",
        matchedIds: null,
        unavailableIds: new Set(),
      }}
    >
      <SettingsChoice
        name="difficulty"
        label="Difficulty"
        value="easy"
        options={OPTIONS}
        onChange={onChange}
      />
    </SettingsViewContext.Provider>,
  );
  return onChange;
}

describe("SettingsChoice", () => {
  it("従来の画面では、選択肢ごとの説明付きラジオカードを出す", () => {
    renderChoice("classic");
    expect(screen.queryByRole("radiogroup")).toBeNull();
    expect(screen.getByText("Gentle effects")).toBeTruthy();
    expect(screen.getByText("Intense effects")).toBeTruthy();
    expect(
      (screen.getByRole("radio", { name: /Easy/ }) as HTMLInputElement).checked,
    ).toBe(true);
  });

  it("新しい画面では、セグメント型と選んでいる選択肢の説明だけを出す", () => {
    const onChange = renderChoice("v2");
    expect(screen.getByRole("radiogroup", { name: "Difficulty" })).toBeTruthy();
    expect(screen.getByText("Gentle effects")).toBeTruthy();
    expect(screen.queryByText("Intense effects")).toBeNull();

    fireEvent.click(screen.getByRole("radio", { name: "Hard" }));
    expect(onChange).toHaveBeenCalledWith("hard");
  });
});
