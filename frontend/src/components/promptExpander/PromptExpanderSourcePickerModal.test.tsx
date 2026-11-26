import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "../../i18n";
import type { PromptExpanderEntry } from "../../apis/promptExpander";
import { adventure } from "../../i18n/ja/adventure";
import type { CharacterPreset } from "../../types";
import PromptExpanderSourcePickerModal from "./PromptExpanderSourcePickerModal";

const mocks = vi.hoisted(() => ({
  listCharacterPresets: vi.fn(),
  fetchGallerySessions: vi.fn(),
  fetchPromptExpanderEntries: vi.fn(),
  setSource: vi.fn(),
  setReference: vi.fn(),
}));

vi.mock("../../apis/characters", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../apis/characters")>()),
  listCharacterPresets: mocks.listCharacterPresets,
}));

vi.mock("../../apis/gallery", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../apis/gallery")>()),
  fetchGallerySessions: mocks.fetchGallerySessions,
}));

vi.mock("../../apis/promptExpander", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../apis/promptExpander")>()),
  fetchPromptExpanderEntries: mocks.fetchPromptExpanderEntries,
}));

vi.mock("../../contexts/PromptExpanderContext", () => ({
  usePromptExpander: () => ({
    source: null,
    reference: null,
    setSource: mocks.setSource,
    setReference: mocks.setReference,
  }),
}));

// jsdom には IntersectionObserver が無いため、一覧の無限スクロール用に空の実装を置く
vi.stubGlobal(
  "IntersectionObserver",
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
);

const entry = {
  id: "e1",
  instruction: "制服に着替える",
  final_prompt: "1girl, school uniform",
  image_url: "/prompt-expander/images/e1",
  transparent_background: false,
} as PromptExpanderEntry;

const sakura = {
  id: "p1",
  name: "サクラ",
  profile: null,
  thumbnail_url: null,
  portrait_url: "/game/character-presets/p1/images/portrait.png",
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
} as CharacterPreset;

const fetchMock = vi.fn();

beforeEach(() => {
  mocks.fetchPromptExpanderEntries.mockResolvedValue({
    items: [entry],
    page: 1,
    has_more: false,
  });
  mocks.listCharacterPresets.mockResolvedValue([sakura]);
  mocks.fetchGallerySessions.mockResolvedValue({
    sessions: [],
    has_more: false,
  });
  // Node の Response は jsdom の Blob を扱えないため、blob() を返す最小の応答にする
  fetchMock.mockResolvedValue({
    ok: true,
    status: 200,
    blob: async () => new Blob(["png"], { type: "image/png" }),
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  localStorage.clear();
});

function renderPicker(target?: "source" | "reference") {
  const onClose = vi.fn();
  render(
    <MemoryRouter>
      <PromptExpanderSourcePickerModal open onClose={onClose} target={target} />
    </MemoryRouter>,
  );
  return { onClose };
}

describe("PromptExpanderSourcePickerModal", () => {
  it("TSFシナリオと同じ4タブを出し、Prompt Expander のタブで開く", () => {
    renderPicker();
    const tabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
    expect(tabs).toEqual([
      "セッション",
      "お気に入り",
      adventure.sourcePicker.tabPromptExpander,
      adventure.sourcePicker.tabCharacters,
    ]);
    expect(
      screen
        .getByRole("tab", { name: adventure.sourcePicker.tabPromptExpander })
        .getAttribute("aria-selected"),
    ).toBe("true");
  });

  it("エントリを選ぶと entry として i2i 元に入れる", async () => {
    const { onClose } = renderPicker();
    fireEvent.click(await screen.findByRole("button", { name: /制服/ }));
    expect(mocks.setSource).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "entry",
        entryId: "e1",
        label: "制服に着替える",
      }),
    );
    expect(onClose).toHaveBeenCalled();
  });

  it("キャラクターを選ぶと立ち絵を取り込み、upload として参照画像に入れる", async () => {
    const { onClose } = renderPicker("reference");
    fireEvent.click(
      screen.getByRole("tab", { name: adventure.sourcePicker.tabCharacters }),
    );
    fireEvent.click(await screen.findByRole("button", { name: /サクラ/ }));

    await waitFor(() => expect(mocks.setReference).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/game/character-presets/p1/images/portrait.png",
    );
    const assigned = mocks.setReference.mock.calls[0][0];
    expect(assigned).toMatchObject({ kind: "upload", label: "サクラ" });
    expect(assigned.uploadDataUrl).toMatch(/^data:image\/png;base64,/);
    expect(assigned.thumbnailUrl).toBe(assigned.uploadDataUrl);
    expect(mocks.setSource).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("立ち絵を取り込めなければエラーを出し、選択は変えない", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 404 });
    const { onClose } = renderPicker();
    fireEvent.click(
      screen.getByRole("tab", { name: adventure.sourcePicker.tabCharacters }),
    );
    fireEvent.click(await screen.findByRole("button", { name: /サクラ/ }));

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(mocks.setSource).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });
});
