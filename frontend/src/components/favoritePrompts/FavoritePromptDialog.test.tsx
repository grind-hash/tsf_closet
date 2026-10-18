import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { useEffect, useRef, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "../../i18n";
import { FavoritePromptProvider } from "../../contexts/FavoritePromptContext";
import { NotificationProvider } from "../../contexts/NotificationContext";
import { useInsertAtCaret } from "../../hooks/useInsertAtCaret";
import {
  FavoritePromptInsertButton,
  FavoritePromptSaveButton,
} from "./FavoritePromptButtons";
import FavoritePromptHost from "./FavoritePromptHost";

const STORAGE_NOTE = /NovelAI のプロンプトチャンクには登録されません/;

const listBody = {
  categories: [
    {
      id: "cat-1",
      label: "衣装",
      color: "#3B82F6",
      sort_order: 0,
      created_at: "2026-10-14T00:00:00",
      updated_at: "2026-10-14T00:00:00",
    },
  ],
  prompts: [
    {
      id: "p-1",
      category_id: null,
      label: "笑顔",
      content: "smile, ",
      color: "#6B7280",
      sort_order: 0,
      created_at: "2026-10-14T00:00:00",
      updated_at: "2026-10-14T00:00:00",
    },
    {
      id: "p-2",
      category_id: "cat-1",
      label: "白ワンピース",
      content: "white sundress",
      color: "#6B7280",
      sort_order: 1,
      created_at: "2026-10-14T00:00:00",
      updated_at: "2026-10-14T00:00:00",
    },
  ],
};

const importedPrompt = {
  id: "p-3",
  category_id: "cat-2",
  label: "ポニーテール",
  content: "ponytail",
  color: "#6B7280",
  sort_order: 2,
  created_at: "2026-10-17T00:00:00",
  updated_at: "2026-10-17T00:00:00",
};

const importedCategory = {
  id: "cat-2",
  label: "髪型",
  color: "#6B7280",
  sort_order: 1,
  created_at: "2026-10-17T00:00:00",
  updated_at: "2026-10-17T00:00:00",
};

const overwritingPreview = {
  create_count: 1,
  overwrites: [{ category: "衣装", label: "白ワンピース" }],
  new_categories: ["髪型"],
};

let importPreview: typeof overwritingPreview = overwritingPreview;
let reorderStatus = 200;

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
    const url = String(input);
    if (url === "/api/favorite-prompts" && !init?.method) {
      return jsonResponse(200, listBody);
    }
    if (url === "/api/favorite-prompts" && init?.method === "POST") {
      const body = JSON.parse(String(init.body));
      return jsonResponse(201, {
        id: "p-new",
        sort_order: 2,
        created_at: "2026-10-14T00:00:00",
        updated_at: "2026-10-14T00:00:00",
        ...body,
      });
    }
    if (url.startsWith("/api/favorite-prompts/export?")) {
      return {
        ok: true,
        status: 200,
        blob: async () => new Blob(["csv"]),
      } as unknown as Response;
    }
    if (url === "/api/favorite-prompts/import/preview") {
      return jsonResponse(200, importPreview);
    }
    if (url === "/api/favorite-prompts/order" && init?.method === "PUT") {
      if (reorderStatus !== 200) return jsonResponse(reorderStatus, null);
      const { prompts } = JSON.parse(String(init.body)) as {
        prompts: { id: string; category_id: string | null }[];
      };
      return jsonResponse(200, {
        categories: listBody.categories,
        prompts: prompts.map((placed, index) => ({
          ...listBody.prompts.find((p) => p.id === placed.id),
          category_id: placed.category_id,
          sort_order: index,
        })),
      });
    }
    if (url === "/api/favorite-prompts/import") {
      return jsonResponse(200, {
        ...importPreview,
        categories: [...listBody.categories, importedCategory],
        prompts: [...listBody.prompts, importedPrompt],
      });
    }
    return jsonResponse(500, null);
  },
);

function calledUrls(): string[] {
  return fetchMock.mock.calls.map(([input]) => String(input));
}

async function openTransferView() {
  fireEvent.click(
    screen.getByRole("button", { name: "お気に入りプロンプトを挿入" }),
  );
  await screen.findByRole("button", { name: "白ワンピース" });
  fireEvent.click(
    screen.getByRole("button", {
      name: "ファイルに書き出す / ファイルから読み込む",
    }),
  );
}

/** jsdom には DragEvent が無いため、座標と dataTransfer を持つ MouseEvent で代用する */
function drag(element: Element, type: string, clientX = 0) {
  const event = new MouseEvent(type, {
    bubbles: true,
    cancelable: true,
    clientX,
  });
  Object.defineProperty(event, "dataTransfer", {
    value: { setData: vi.fn(), effectAllowed: "", dropEffect: "" },
  });
  fireEvent(element, event);
}

function chipOf(label: string): HTMLElement {
  return screen
    .getByRole("button", { name: label })
    .closest("li") as HTMLElement;
}

function chipLabels(container: HTMLElement): string[] {
  return [...container.querySelectorAll(".favorite-prompts__chip-label")].map(
    (el) => el.textContent ?? "",
  );
}

async function openPicker() {
  fireEvent.click(
    screen.getByRole("button", { name: "お気に入りプロンプトを挿入" }),
  );
  await screen.findByRole("button", { name: "白ワンピース" });
}

function chooseImportFile(file: File) {
  fireEvent.change(screen.getByTestId("favorite-prompts-import-input"), {
    target: { files: [file] },
  });
}

/** 挿入先の入力欄と、各ボタンを並べたテスト用の画面 */
function Harness({ onParentEscape }: { onParentEscape?: () => void }) {
  const [value, setValue] = useState("1girl");
  const ref = useRef<HTMLTextAreaElement>(null);
  const insert = useInsertAtCaret(ref, value, setValue);

  // 親モーダルの Escape 処理（window の bubble 段）を模す
  useEffect(() => {
    if (!onParentEscape) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onParentEscape();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onParentEscape]);

  return (
    <div>
      <textarea
        ref={ref}
        aria-label="target"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <FavoritePromptInsertButton onInsert={insert} />
      <FavoritePromptSaveButton text="1girl, red dress" />
    </div>
  );
}

function renderHarness(onParentEscape?: () => void) {
  return render(
    <NotificationProvider>
      <FavoritePromptProvider>
        <Harness onParentEscape={onParentEscape} />
        <FavoritePromptHost />
      </FavoritePromptProvider>
    </NotificationProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  importPreview = overwritingPreview;
  reorderStatus = 200;
  fetchMock.mockClear();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("FavoritePromptDialog", () => {
  it("lists prompts with the storage note and inserts the clicked one", async () => {
    renderHarness();
    fireEvent.click(
      screen.getByRole("button", { name: "お気に入りプロンプトを挿入" }),
    );

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByText(STORAGE_NOTE)).toBeTruthy();
    const chip = await screen.findByRole("button", { name: "白ワンピース" });
    expect(screen.getByRole("button", { name: /^衣装/ })).toBeTruthy();

    // ホバー中のチップは下部に全文を出す
    fireEvent.mouseEnter(chip);
    expect(screen.getByText("white sundress")).toBeTruthy();

    fireEvent.click(chip);
    expect(screen.queryByRole("dialog")).toBeNull();
    const target = screen.getByLabelText("target") as HTMLTextAreaElement;
    expect(target.value).toBe("1girl, white sundress");
  });

  it("opens the save form with the text prefilled and saves only on submit", async () => {
    renderHarness();
    fireEvent.click(
      screen.getByRole("button", { name: "お気に入りプロンプトに保存" }),
    );

    expect(screen.getByText(STORAGE_NOTE)).toBeTruthy();
    const content = screen.getByLabelText("内容") as HTMLTextAreaElement;
    expect(content.value).toBe("1girl, red dress");
    const saveButton = screen.getByRole("button", {
      name: "保存",
    }) as HTMLButtonElement;
    expect(saveButton.disabled).toBe(true);
    expect(
      fetchMock.mock.calls.some(([, init]) => init?.method === "POST"),
    ).toBe(false);

    fireEvent.change(screen.getByLabelText("名前"), {
      target: { value: "赤ドレス" },
    });
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    const post = fetchMock.mock.calls.find(
      ([, init]) => init?.method === "POST",
    );
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      label: "赤ドレス",
      content: "1girl, red dress",
      color: "#6B7280",
      category_id: null,
    });
  });

  it("closes only itself on Escape, not the parent modal", async () => {
    const onParentEscape = vi.fn();
    renderHarness(onParentEscape);
    fireEvent.click(
      screen.getByRole("button", { name: "お気に入りプロンプトを挿入" }),
    );
    await screen.findByRole("button", { name: "笑顔" });

    fireEvent.keyDown(document.body, { key: "Escape" });

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(onParentEscape).not.toHaveBeenCalled();
  });

  it("lists overwrite targets and imports only after confirmation", async () => {
    const onParentEscape = vi.fn();
    renderHarness(onParentEscape);
    await openTransferView();

    chooseImportFile(
      new File(["名前,内容\n"], "favorites.csv", { type: "text/csv" }),
    );

    const message = await screen.findByText(
      "以下の 1 件のお気に入りプロンプトが上書きされますが、よろしいですか？",
    );
    const confirm = message.closest(".confirm-dialog") as HTMLElement;
    const item = within(confirm).getByText("白ワンピース").closest("li");
    expect(within(item as HTMLElement).getByText("衣装")).toBeTruthy();
    expect(
      within(confirm).getByText("このほかに 1 件を新しく追加します。"),
    ).toBeTruthy();
    expect(
      within(confirm).getByText("新しく作るカテゴリー: 髪型"),
    ).toBeTruthy();
    expect(calledUrls()).not.toContain("/api/favorite-prompts/import");

    // 確認中の Escape では背後のダイアログも親モーダルも閉じない。
    // 確認ダイアログの開閉は effect で親へ伝わるため、反映を待ってから押す
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.getByText(/上書きされますが/)).toBeTruthy();
    expect(onParentEscape).not.toHaveBeenCalled();

    fireEvent.click(
      within(confirm).getByRole("button", { name: "上書きして読み込む" }),
    );

    // 取り込み後は一覧へ戻り、新しいカテゴリーとプロンプトが並ぶ
    expect(
      await screen.findByRole("button", { name: "ポニーテール" }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: /^髪型/ })).toBeTruthy();
    const importCall = fetchMock.mock.calls.find(
      ([input]) => String(input) === "/api/favorite-prompts/import",
    );
    const body = importCall?.[1]?.body;
    expect(body).toBeInstanceOf(FormData);
    expect(((body as FormData).get("file") as File).name).toBe("favorites.csv");
  });

  it("does not import when the overwrite is cancelled", async () => {
    renderHarness();
    await openTransferView();
    chooseImportFile(new File(["{}"], "favorites.json"));

    fireEvent.click(await screen.findByRole("button", { name: "キャンセル" }));

    expect(screen.queryByText(/上書きされますが/)).toBeNull();
    expect(calledUrls()).not.toContain("/api/favorite-prompts/import");
    expect(
      screen.getByRole("button", { name: "ファイルを選んで読み込む" }),
    ).toBeTruthy();
  });

  it("imports right away when nothing would be overwritten", async () => {
    importPreview = { create_count: 1, overwrites: [], new_categories: [] };
    renderHarness();
    await openTransferView();
    chooseImportFile(new File(["名前,内容\n"], "favorites.csv"));

    expect(
      await screen.findByRole("button", { name: "ポニーテール" }),
    ).toBeTruthy();
    expect(screen.queryByText(/上書きされますが/)).toBeNull();
    expect(calledUrls()).toContain("/api/favorite-prompts/import");
  });

  it("exports CSV with headers in the display language", async () => {
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:favorites"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    renderHarness();
    await openTransferView();

    fireEvent.click(
      screen.getByRole("button", { name: "CSV ファイルに書き出す" }),
    );

    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(calledUrls()).toContain(
      "/api/favorite-prompts/export?format=csv&lang=ja",
    );
    const link = click.mock.contexts[0] as HTMLAnchorElement;
    expect(link.download).toMatch(/^tsf-closet-favorite-prompts-\d{8}\.csv$/);
    click.mockRestore();
  });

  it("moves a prompt into a category by dropping it before a chip", async () => {
    renderHarness();
    await openPicker();
    const source = chipOf("笑顔");
    const target = chipOf("白ワンピース");
    vi.spyOn(target, "getBoundingClientRect").mockReturnValue({
      left: 100,
      width: 100,
    } as DOMRect);

    drag(source, "dragstart");
    // ドラッグ中は各グループの末尾にドロップ枠が出る
    expect(await screen.findAllByText("ここに移動")).toHaveLength(2);

    // 左半分の上では直前に挿入位置の縦線を出す
    drag(target, "dragover", 120);
    expect(target.classList.contains("is-drop-before")).toBe(true);
    drag(target, "drop", 120);

    const outfit = screen
      .getByRole("button", { name: /^衣装/ })
      .closest("section") as HTMLElement;
    expect(chipLabels(outfit)).toEqual(["笑顔", "白ワンピース"]);
    expect(screen.queryByText("ここに移動")).toBeNull();
    await waitFor(() =>
      expect(calledUrls()).toContain("/api/favorite-prompts/order"),
    );
    const put = fetchMock.mock.calls.find(
      ([input]) => String(input) === "/api/favorite-prompts/order",
    );
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({
      prompts: [
        { id: "p-1", category_id: "cat-1" },
        { id: "p-2", category_id: "cat-1" },
      ],
    });
  });

  it("keeps a collapsed category closed after reopening the dialog", async () => {
    renderHarness();
    await openPicker();
    fireEvent.click(screen.getByRole("button", { name: /^衣装/ }));
    expect(screen.queryByRole("button", { name: "白ワンピース" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "閉じる" }));
    cleanup();

    renderHarness();
    fireEvent.click(
      screen.getByRole("button", { name: "お気に入りプロンプトを挿入" }),
    );
    const header = await screen.findByRole("button", { name: /^衣装/ });
    expect(header.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("button", { name: "白ワンピース" })).toBeNull();
  });

  it("expands and collapses every category from the header button", async () => {
    renderHarness();
    await openPicker();

    fireEvent.click(
      screen.getByRole("button", { name: "すべてのカテゴリーを閉じる" }),
    );
    expect(screen.queryByRole("button", { name: "白ワンピース" })).toBeNull();
    expect(
      screen
        .getByRole("button", { name: /^衣装/ })
        .getAttribute("aria-expanded"),
    ).toBe("false");

    fireEvent.click(
      screen.getByRole("button", { name: "すべてのカテゴリーを開く" }),
    );
    expect(screen.getByRole("button", { name: "白ワンピース" })).toBeTruthy();
  });

  it("drops onto a collapsed category header and restores the order on failure", async () => {
    reorderStatus = 500;
    renderHarness();
    await openPicker();
    const header = screen.getByRole("button", { name: /^衣装/ });
    fireEvent.click(header);
    expect(screen.queryByRole("button", { name: "白ワンピース" })).toBeNull();

    drag(chipOf("笑顔"), "dragstart");
    drag(header, "dragover");
    expect(
      header
        .closest(".favorite-prompts__category-head")
        ?.classList.contains("is-drop-target"),
    ).toBe(true);
    drag(header, "drop");

    // 保存を待たずに折りたたみ中の衣装へ移り、失敗したら未分類へ戻る
    const body = document.querySelector(
      ".favorite-prompts__body",
    ) as HTMLElement;
    expect(chipLabels(body)).toEqual([]);
    expect(header.textContent).toContain("2");
    await waitFor(() => expect(chipLabels(body)).toEqual(["笑顔"]));
    expect(header.textContent).toContain("1");
    expect(calledUrls()).toContain("/api/favorite-prompts/order");
  });
});
