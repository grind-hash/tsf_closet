import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import "../../i18n";
import { adventure } from "../../i18n/ja/adventure";
import { gallery } from "../../i18n/ja/gallery";
import type { CharacterPreset, GallerySession } from "../../types";
import AdventureSessionPickerModal, {
  type AdventureSourceSelection,
  selectionFromCharacterPreset,
} from "./AdventureSessionPickerModal";
import AdventureSourceSelectionCard from "./AdventureSourceSelectionCard";

const mocks = vi.hoisted(() => ({
  listCharacterPresets: vi.fn(),
  fetchGallerySessions: vi.fn(),
  fetchGallerySession: vi.fn(),
  fetchGalleryList: vi.fn(),
}));

vi.mock("../../apis/characters", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../apis/characters")>()),
  listCharacterPresets: mocks.listCharacterPresets,
}));

vi.mock("../../apis/gallery", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../apis/gallery")>()),
  fetchGallerySessions: mocks.fetchGallerySessions,
  fetchGallerySession: mocks.fetchGallerySession,
  fetchGalleryList: mocks.fetchGalleryList,
}));

function session(overrides: Partial<GallerySession> = {}): GallerySession {
  return {
    session_id: "s-old",
    character_name: "ナオ",
    thumbnail_url: "/history/images/h-latest",
    item_count: 24,
    first_timestamp: "2026-10-03T09:00:00",
    last_timestamp: "2026-10-05T09:00:00",
    ...overrides,
  };
}

// 読み込み済みの一覧に無い、古いセッションの途中の時点を選んでいる状態
const oldPointSelection: AdventureSourceSelection = {
  sessionId: "s-old",
  historyId: "h-12",
  characterName: "ナオ",
  thumbnailUrl: "/history/images/h-12",
  pointLabel: "スカートを短くして",
  origin: "session",
};

// jsdom には IntersectionObserver が無いため、一覧の無限スクロール用に空の実装を置く
vi.stubGlobal(
  "IntersectionObserver",
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AdventureSessionPickerModal の選択中カード", () => {
  it("一覧に読み込まれていないセッションでも、先頭に選択中として出す", async () => {
    mocks.fetchGallerySessions.mockResolvedValue({
      sessions: [session({ session_id: "s-new", character_name: "ユウ" })],
      has_more: true,
    });
    mocks.fetchGallerySession.mockResolvedValue(session());
    mocks.fetchGalleryList.mockResolvedValue({ items: [], has_more: false });
    render(
      <MemoryRouter>
        <AdventureSessionPickerModal
          title="開始セッション"
          selected={oldPointSelection}
          onSelect={vi.fn()}
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );

    const pin = screen.getByRole("region", {
      name: adventure.sourcePicker.currentHeading,
    });
    expect(pin.textContent).toContain("ナオ");
    expect(pin.textContent).toContain("スカートを短くして");
    await waitFor(() => expect(pin.textContent).toContain("24枚"));
    expect(mocks.fetchGallerySession).toHaveBeenCalledWith("s-old");

    // 選択中のセッションの時点一覧へ直接移れる
    fireEvent.click(
      screen.getByRole("button", {
        name: adventure.sourcePicker.openSelectedHistory,
      }),
    );
    expect(
      await screen.findByRole("button", { name: gallery.backToSessions }),
    ).toBeTruthy();
    await waitFor(() =>
      expect(mocks.fetchGalleryList).toHaveBeenCalledWith(1, 30, "s-old"),
    );
    // 開いた後は同じセッションへの移動ボタンを出さない
    expect(
      screen.queryByRole("button", {
        name: adventure.sourcePicker.openSelectedHistory,
      }),
    ).toBeNull();
  });

  it("未選択なら選択中カードを出さない", () => {
    mocks.fetchGallerySessions.mockResolvedValue({
      sessions: [],
      has_more: false,
    });
    render(
      <MemoryRouter>
        <AdventureSessionPickerModal
          title="開始セッション"
          selected={null}
          onSelect={vi.fn()}
          onClose={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(
      screen.queryByRole("region", {
        name: adventure.sourcePicker.currentHeading,
      }),
    ).toBeNull();
    expect(mocks.fetchGallerySession).not.toHaveBeenCalled();
  });

  it("キャラクターの一覧を読み終えてから、選択中のキャラクターへフォーカスする", async () => {
    const presets = ["p1", "p2", "p3"].map(
      (id) =>
        ({
          id,
          name: `キャラ${id}`,
          profile: null,
          thumbnail_url: null,
          portrait_url: `/game/character-presets/${id}/images/portrait.png`,
        }) as CharacterPreset,
    );
    mocks.listCharacterPresets.mockResolvedValue(presets);
    render(
      <MemoryRouter>
        <AdventureSessionPickerModal
          title="主人公"
          selected={selectionFromCharacterPreset(presets[2])}
          onSelect={vi.fn()}
          onClose={vi.fn()}
          characters="only"
        />
      </MemoryRouter>,
    );

    const tile = await screen.findByRole("button", { name: /キャラp3/ });
    await waitFor(() => expect(document.activeElement).toBe(tile));
  });
});

describe("AdventureSourceSelectionCard", () => {
  it("セッションの情報があれば、その名前と枚数・開始日を出す", () => {
    render(
      <AdventureSourceSelectionCard
        selection={{ ...oldPointSelection, characterName: "エミ" }}
        sessionInfo={session()}
      />,
    );
    const card = screen.getByRole("group");
    expect(card.textContent).toContain("ナオ");
    expect(card.textContent).not.toContain("エミ");
    expect(card.textContent).toContain("24枚・2026/10/3開始");
  });

  it("セッションの情報が無いあいだは選択時の名前を出し、枚数は出さない", () => {
    render(
      <AdventureSourceSelectionCard
        selection={oldPointSelection}
        sessionInfo={null}
      />,
    );
    const card = screen.getByRole("group");
    expect(card.textContent).toContain("ナオ");
    expect(card.textContent).not.toContain("枚");
  });
});
