import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "../../i18n";
import {
  FavoritePromptProvider,
  useFavoritePrompts,
} from "../FavoritePromptContext";
import { NotificationProvider, useNotification } from "../NotificationContext";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  } as unknown as Response;
}

const timestamps = {
  created_at: "2026-10-14T00:00:00",
  updated_at: "2026-10-14T00:00:00",
};

const fetchMock = vi.fn(
  async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/favorite-prompts" && !init?.method) {
      return jsonResponse(200, {
        categories: [
          {
            id: "cat-1",
            label: "衣装",
            color: "#3B82F6",
            sort_order: 0,
            ...timestamps,
          },
        ],
        prompts: [
          {
            id: "p-1",
            category_id: "cat-1",
            label: "白ワンピース",
            content: "white sundress",
            color: "#6B7280",
            sort_order: 0,
            ...timestamps,
          },
        ],
      });
    }
    if (url === "/api/favorite-prompts/categories/cat-1") {
      return jsonResponse(200, { success: true, deleted: true });
    }
    if (url === "/api/favorite-prompts" && init?.method === "POST") {
      return jsonResponse(422, {
        detail: { code: "label_required", message: "名前を入力してください" },
      });
    }
    return jsonResponse(500, null);
  },
);

function Probe() {
  const {
    prompts,
    categories,
    loaded,
    ensureLoaded,
    deleteCategory,
    createPrompt,
  } = useFavoritePrompts();
  return (
    <>
      <div data-testid="state">
        {loaded
          ? `${categories.length}:${prompts
              .map((p) => `${p.label}@${p.category_id ?? "none"}`)
              .join(",")}`
          : "loading"}
      </div>
      <button type="button" onClick={() => void ensureLoaded()}>
        load
      </button>
      <button type="button" onClick={() => void deleteCategory("cat-1")}>
        delete-category
      </button>
      <button
        type="button"
        onClick={() =>
          void createPrompt({
            label: " ",
            content: "x",
            color: "#6B7280",
            category_id: null,
          })
        }
      >
        create-invalid
      </button>
    </>
  );
}

function NotificationList() {
  const { notifications } = useNotification();
  return (
    <ul>
      {notifications.map((n) => (
        <li key={n.id}>{n.message}</li>
      ))}
    </ul>
  );
}

function renderProbe() {
  return render(
    <NotificationProvider>
      <FavoritePromptProvider>
        <Probe />
      </FavoritePromptProvider>
      <NotificationList />
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

describe("FavoritePromptContext", () => {
  it("loads once and moves prompts to uncategorized when their category is deleted", async () => {
    renderProbe();
    fireEvent.click(screen.getByText("load"));
    fireEvent.click(screen.getByText("load"));
    await waitFor(() => {
      expect(screen.getByTestId("state").textContent).toBe(
        "1:白ワンピース@cat-1",
      );
    });
    const listCalls = fetchMock.mock.calls.filter(
      ([url, init]) => url === "/api/favorite-prompts" && !init?.method,
    );
    expect(listCalls).toHaveLength(1);

    fireEvent.click(screen.getByText("delete-category"));
    await waitFor(() => {
      expect(screen.getByTestId("state").textContent).toBe(
        "0:白ワンピース@none",
      );
    });
  });

  it("reports API errors as a notification", async () => {
    renderProbe();
    fireEvent.click(screen.getByText("create-invalid"));
    expect(await screen.findByText("名前を入力してください")).toBeTruthy();
  });
});
