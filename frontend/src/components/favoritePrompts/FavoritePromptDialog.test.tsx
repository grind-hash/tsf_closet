import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
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
    return jsonResponse(500, null);
  },
);

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
});
