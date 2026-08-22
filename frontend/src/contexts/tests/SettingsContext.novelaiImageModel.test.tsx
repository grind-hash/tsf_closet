import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsProvider, useSettings } from "../SettingsContext";

const fetchMock = vi.fn(
  async (_input: RequestInfo | URL, _init?: RequestInit) =>
    ({ ok: false }) as Response,
);

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  fetchMock.mockClear();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function ImageModelProbe() {
  const {
    state,
    setNovelaiImageModel,
    setNovelaiCuratedImageModel,
    setNsfwMode,
    setImageProvider,
    effectiveNovelaiImageModel,
    isNovelaiV5Active,
  } = useSettings();

  return (
    <>
      <div data-testid="nsfw-model">{state.novelaiImageModel}</div>
      <div data-testid="sfw-model">{state.novelaiCuratedImageModel}</div>
      <div data-testid="effective-model">{effectiveNovelaiImageModel}</div>
      <div data-testid="v5-active">{isNovelaiV5Active ? "on" : "off"}</div>
      <button
        type="button"
        onClick={() => setNovelaiImageModel("nai-diffusion-5-full")}
      >
        select-v5-full
      </button>
      <button
        type="button"
        onClick={() => setNovelaiCuratedImageModel("nai-diffusion-5-curated")}
      >
        select-v5-curated
      </button>
      <button type="button" onClick={() => setNsfwMode(true)}>
        enable-nsfw
      </button>
      <button type="button" onClick={() => setImageProvider("novelai")}>
        use-novelai
      </button>
    </>
  );
}

describe("SettingsContext novelai image model selection", () => {
  it("defaults to the V4.5 models", () => {
    render(
      <SettingsProvider>
        <ImageModelProbe />
      </SettingsProvider>,
    );

    expect(screen.getByTestId("nsfw-model").textContent).toBe(
      "nai-diffusion-4-5-full",
    );
    expect(screen.getByTestId("sfw-model").textContent).toBe(
      "nai-diffusion-4-5-curated",
    );
    expect(screen.getByTestId("v5-active").textContent).toBe("off");
  });

  it("persists selections to the backend, not to localStorage", async () => {
    render(
      <SettingsProvider>
        <ImageModelProbe />
      </SettingsProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "select-v5-full" }));
    expect(screen.getByTestId("nsfw-model").textContent).toBe(
      "nai-diffusion-5-full",
    );

    await waitFor(() => {
      const putCall = fetchMock.mock.calls.find(
        ([url, init]) =>
          url === "/api/settings/user" &&
          init?.method === "PUT" &&
          String(init.body).includes("novelai_image_model"),
      );
      expect(putCall).toBeTruthy();
      if (!putCall) throw new Error("PUT call not found");
      expect(String(putCall[1]?.body)).toContain("nai-diffusion-5-full");
    });

    await waitFor(() => {
      const saved = JSON.parse(localStorage.getItem("app_settings") ?? "{}");
      expect(saved).not.toHaveProperty("novelaiImageModel");
      expect(saved).not.toHaveProperty("novelaiCuratedImageModel");
    });
  });

  it("derives the effective model and V5 flag from nsfw mode and provider", () => {
    render(
      <SettingsProvider>
        <ImageModelProbe />
      </SettingsProvider>,
    );

    // 既定: nsfw OFF → curated 側が実効
    expect(screen.getByTestId("effective-model").textContent).toBe(
      "nai-diffusion-4-5-curated",
    );

    fireEvent.click(screen.getByRole("button", { name: "select-v5-curated" }));
    expect(screen.getByTestId("effective-model").textContent).toBe(
      "nai-diffusion-5-curated",
    );
    // provider が novelai でない間は V5 扱いにならない
    expect(screen.getByTestId("v5-active").textContent).toBe("off");

    fireEvent.click(screen.getByRole("button", { name: "use-novelai" }));
    expect(screen.getByTestId("v5-active").textContent).toBe("on");

    // nsfw ON へ切替 → full 側(既定4.5)が実効になり V5 ではなくなる
    fireEvent.click(screen.getByRole("button", { name: "enable-nsfw" }));
    expect(screen.getByTestId("effective-model").textContent).toBe(
      "nai-diffusion-4-5-full",
    );
    expect(screen.getByTestId("v5-active").textContent).toBe("off");

    fireEvent.click(screen.getByRole("button", { name: "select-v5-full" }));
    expect(screen.getByTestId("v5-active").textContent).toBe("on");
  });
});
