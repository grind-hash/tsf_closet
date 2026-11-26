import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import "../../i18n";
import { adventure } from "../../i18n/ja/adventure";
import { characters } from "../../i18n/ja/characters";
import type { CharacterPreset } from "../../types";
import AdventureCharacterPresetGrid from "./AdventureCharacterPresetGrid";
import AdventureSessionPickerModal, {
  selectionFromCharacterPreset,
} from "./AdventureSessionPickerModal";

const mocks = vi.hoisted(() => ({
  listCharacterPresets: vi.fn(),
  fetchGallerySessions: vi.fn(),
}));

vi.mock("../../apis/characters", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../apis/characters")>()),
  listCharacterPresets: mocks.listCharacterPresets,
}));

vi.mock("../../apis/gallery", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../apis/gallery")>()),
  fetchGallerySessions: mocks.fetchGallerySessions,
}));

function preset(overrides: Partial<CharacterPreset>): CharacterPreset {
  return {
    id: "p1",
    name: "サクラ",
    appearance_natural: "",
    appearance_tags: "pink hair",
    default_position: "center",
    negative_tags: "",
    profile: null,
    thumbnail_url: null,
    avatar_model_id: null,
    voice: null,
    portrait_url: "/game/character-presets/p1/images/portrait.png",
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    ...overrides,
  } as CharacterPreset;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  localStorage.clear();
});

function tileNames(): string[] {
  const grid = screen.getByRole("group", {
    name: adventure.sourcePicker.tabCharacters,
  });
  return within(grid)
    .getAllByRole("button")
    .map((tile) => tile.querySelector(".adventure-session-picker__tile-name"))
    .map((name) => name?.textContent ?? "");
}

describe("AdventureCharacterPresetGrid", () => {
  it("立ち絵の無いキャラクターは理由を添えて選べなくする", async () => {
    mocks.listCharacterPresets.mockResolvedValue([
      preset({ id: "p1", name: "サクラ" }),
      preset({ id: "p2", name: "ユウ", portrait_url: null }),
    ]);
    const onSelect = vi.fn();
    render(
      <MemoryRouter>
        <AdventureCharacterPresetGrid
          selectedPresetId="p1"
          onSelect={onSelect}
        />
      </MemoryRouter>,
    );

    const usable = await screen.findByRole("button", { name: /サクラ/ });
    const disabled = screen.getByRole("button", { name: /ユウ/ });
    expect(usable.getAttribute("data-selected")).toBe("true");
    expect((disabled as HTMLButtonElement).disabled).toBe(true);
    expect(
      screen.getByText(adventure.sourcePicker.characterNoPortrait),
    ).toBeTruthy();

    fireEvent.click(usable);
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ id: "p1" }),
    );
  });

  it("キャラクターがいなければキャラクターメイクへの導線を出す", async () => {
    mocks.listCharacterPresets.mockResolvedValue([]);
    render(
      <MemoryRouter>
        <AdventureCharacterPresetGrid
          selectedPresetId={null}
          onSelect={vi.fn()}
        />
      </MemoryRouter>,
    );
    const link = await screen.findByRole("link", {
      name: adventure.sourcePicker.characterCreateLink,
    });
    expect(link.getAttribute("href")).toBe("/characters");
  });
});

describe("AdventureCharacterPresetGrid の並び順", () => {
  const sortable = [
    preset({ id: "p1", name: "サクラ", created_at: "2026-10-01T00:00:00Z" }),
    preset({ id: "p2", name: "アオイ", created_at: "2026-10-05T00:00:00Z" }),
    preset({ id: "p3", name: "ユウ", created_at: "2026-10-03T00:00:00Z" }),
  ];

  it("初期は作成日の新しい順に並べる", async () => {
    mocks.listCharacterPresets.mockResolvedValue(sortable);
    render(
      <MemoryRouter>
        <AdventureCharacterPresetGrid
          selectedPresetId={null}
          onSelect={vi.fn()}
        />
      </MemoryRouter>,
    );
    await screen.findByRole("button", { name: /サクラ/ });
    expect(tileNames()).toEqual(["アオイ", "ユウ", "サクラ"]);
  });

  it("並び順を変えると並べ替え、キャラクター画面と共有する保存先に書く", async () => {
    mocks.listCharacterPresets.mockResolvedValue(sortable);
    render(
      <MemoryRouter>
        <AdventureCharacterPresetGrid
          selectedPresetId={null}
          onSelect={vi.fn()}
        />
      </MemoryRouter>,
    );
    await screen.findByRole("button", { name: /サクラ/ });
    fireEvent.change(
      screen.getByRole("combobox", { name: characters.sort.label }),
      { target: { value: "name_asc" } },
    );
    expect(tileNames()).toEqual(["アオイ", "サクラ", "ユウ"]);
    expect(localStorage.getItem("character_sort_order")).toBe("name_asc");
  });

  it("保存された並び順で開き、不正な保存値なら既定に戻す", async () => {
    mocks.listCharacterPresets.mockResolvedValue(sortable);
    localStorage.setItem("character_sort_order", "created_asc");
    const { unmount } = render(
      <MemoryRouter>
        <AdventureCharacterPresetGrid
          selectedPresetId={null}
          onSelect={vi.fn()}
        />
      </MemoryRouter>,
    );
    await screen.findByRole("button", { name: /サクラ/ });
    expect(tileNames()).toEqual(["サクラ", "ユウ", "アオイ"]);
    unmount();

    localStorage.setItem("character_sort_order", "broken");
    render(
      <MemoryRouter>
        <AdventureCharacterPresetGrid
          selectedPresetId={null}
          onSelect={vi.fn()}
        />
      </MemoryRouter>,
    );
    await screen.findByRole("button", { name: /サクラ/ });
    expect(tileNames()).toEqual(["アオイ", "ユウ", "サクラ"]);
  });
});

describe("selectionFromCharacterPreset", () => {
  it("立ち絵・性格・一人称を選択結果に写す", () => {
    const selection = selectionFromCharacterPreset(
      preset({
        thumbnail_url: "/thumb.png",
        profile: {
          personality: " 負けず嫌い ",
          pronoun: "あたし",
        } as CharacterPreset["profile"],
      }),
    );
    expect(selection).toMatchObject({
      sessionId: "",
      characterPresetId: "p1",
      characterName: "サクラ",
      characterPronoun: "あたし",
      thumbnailUrl: "/game/character-presets/p1/images/portrait.png",
      pointLabel: "負けず嫌い",
      origin: "character",
    });
  });
});

describe("AdventureSessionPickerModal characters", () => {
  it("only ではタブ列を出さず、セッションも読み込まない", async () => {
    mocks.listCharacterPresets.mockResolvedValue([preset({})]);
    render(
      <MemoryRouter>
        <AdventureSessionPickerModal
          title="主人公"
          selected={null}
          onSelect={vi.fn()}
          onClose={vi.fn()}
          characters="only"
        />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("button", { name: /サクラ/ })).toBeTruthy();
    expect(screen.queryByRole("tablist")).toBeNull();
    expect(mocks.fetchGallerySessions).not.toHaveBeenCalled();
  });

  it("tab ではキャラクターを選んだ状態で開くとキャラクタータブが開く", async () => {
    mocks.listCharacterPresets.mockResolvedValue([preset({})]);
    mocks.fetchGallerySessions.mockResolvedValue({
      sessions: [],
      has_more: false,
    });
    render(
      <MemoryRouter>
        <AdventureSessionPickerModal
          title="開始セッション"
          selected={selectionFromCharacterPreset(preset({}))}
          onSelect={vi.fn()}
          onClose={vi.fn()}
          characters="tab"
        />
      </MemoryRouter>,
    );
    const tab = screen.getByRole("tab", {
      name: adventure.sourcePicker.tabCharacters,
    });
    expect(tab.getAttribute("aria-selected")).toBe("true");
    const tile = await screen.findByRole("button", { name: /サクラ/ });
    expect(tile.getAttribute("data-selected")).toBe("true");
  });

  it("既定(off)ではキャラクタータブを出さない", () => {
    mocks.fetchGallerySessions.mockResolvedValue({
      sessions: [],
      has_more: false,
    });
    render(
      <MemoryRouter>
        <AdventureSessionPickerModal
          title="主人公にするセッション"
          selected={null}
          onSelect={vi.fn()}
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(
      screen.queryByRole("tab", { name: adventure.sourcePicker.tabCharacters }),
    ).toBeNull();
  });
});
