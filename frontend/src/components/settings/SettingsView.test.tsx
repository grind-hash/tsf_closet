import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  CollapsibleSettingsSection,
  SettingsItem,
  SettingsSection,
  SettingsViewContext,
  type SettingsViewState,
} from "./SettingsView";
import type { SettingsItemId } from "./settingsSearchIndex";

afterEach(cleanup);

function Fixture() {
  return (
    <>
      <SettingsSection category="game" title="Game">
        <SettingsItem id="difficulty">
          <p>difficulty</p>
        </SettingsItem>
        <SettingsItem id="nsfwMode">
          <p>nsfw</p>
        </SettingsItem>
      </SettingsSection>
      <SettingsSection category="display" title="Display">
        <SettingsItem id="fontFamily">
          <p>font</p>
        </SettingsItem>
      </SettingsSection>
      <CollapsibleSettingsSection
        category="avatar"
        title="Avatar"
        summary={null}
        open={false}
        onToggle={() => {}}
        bodyId="avatar-body"
        toggleTestId="avatar-toggle"
      >
        <SettingsItem id="avatarModels">
          <p>avatar</p>
        </SettingsItem>
      </CollapsibleSettingsSection>
    </>
  );
}

function renderWith(view: Partial<SettingsViewState>) {
  const value: SettingsViewState = {
    mode: "v2",
    activeCategory: "game",
    matchedIds: null,
    unavailableIds: new Set(),
    ...view,
  };
  return render(
    <SettingsViewContext.Provider value={value}>
      <Fixture />
    </SettingsViewContext.Provider>,
  );
}

function headings() {
  return screen.queryAllByRole("heading").map((h) => h.textContent);
}

describe("SettingsView", () => {
  it("Provider が無ければ従来どおり、すべて出す", () => {
    render(<Fixture />);
    // 開閉セクションの見出しには開閉マーク(▾)が付く
    expect(headings()).toEqual(["Game", "Display", "▾Avatar"]);
    expect(screen.getByText("font")).toBeTruthy();
    // 従来の画面では開閉ボタンがあり、閉じている間は中身を hidden で残す
    expect(
      screen.getByTestId("avatar-toggle").getAttribute("aria-expanded"),
    ).toBe("false");
    expect(document.getElementById("avatar-body")?.hidden).toBe(true);
  });

  it("v2 で検索していないときは、選択中のカテゴリだけ出す", () => {
    renderWith({ activeCategory: "display" });
    expect(headings()).toEqual(["Display"]);
    expect(screen.getByText("font")).toBeTruthy();
    expect(screen.queryByText("difficulty")).toBeNull();
  });

  it("v2 の開閉セクションは常に開いた状態で出し、開閉ボタンを出さない", () => {
    renderWith({ activeCategory: "avatar" });
    expect(headings()).toEqual(["Avatar"]);
    expect(screen.queryByTestId("avatar-toggle")).toBeNull();
    expect(document.getElementById("avatar-body")?.hidden).toBe(false);
    expect(screen.getByText("avatar")).toBeTruthy();
  });

  it("v2 の検索中は、一致した項目とそのカテゴリだけ出す", () => {
    renderWith({
      activeCategory: "display",
      matchedIds: new Set<SettingsItemId>(["nsfwMode", "avatarModels"]),
    });
    expect(headings()).toEqual(["Game", "Avatar"]);
    expect(screen.getByText("nsfw")).toBeTruthy();
    expect(screen.queryByText("difficulty")).toBeNull();
    expect(screen.queryByText("font")).toBeNull();
  });

  it("表示しない項目は、どのモードでも出さない", () => {
    render(
      <SettingsViewContext.Provider
        value={{
          mode: "classic",
          activeCategory: "game",
          matchedIds: null,
          unavailableIds: new Set<SettingsItemId>(["nsfwMode"]),
        }}
      >
        <Fixture />
      </SettingsViewContext.Provider>,
    );
    expect(screen.getByText("difficulty")).toBeTruthy();
    expect(screen.queryByText("nsfw")).toBeNull();
  });
});
