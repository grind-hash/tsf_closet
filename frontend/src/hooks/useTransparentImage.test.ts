import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useTransparentImage } from "./useTransparentImage";

const retain = vi.hoisted(() =>
  vi.fn(() => ({
    url: Promise.resolve("blob:processed"),
    release: vi.fn(),
  })),
);

vi.mock("../utils/imageAlpha", () => ({
  retainTransparentImage: retain,
}));

describe("useTransparentImage", () => {
  it("passes a null background color through to detect it from the corners", async () => {
    const { result } = renderHook(() =>
      useTransparentImage("/img/a.png", true, {
        targetColor: null,
        threshold: 12,
        featherRadius: 1.8,
      }),
    );

    await waitFor(() => expect(result.current.url).toBe("blob:processed"));
    expect(retain).toHaveBeenLastCalledWith("/img/a.png", {
      targetColor: null,
      threshold: 12,
      featherRadius: 1.8,
    });
  });

  it("keeps the white default when no background color is given", async () => {
    renderHook(() => useTransparentImage("/img/b.png", true, { threshold: 8 }));

    await waitFor(() =>
      expect(retain).toHaveBeenLastCalledWith("/img/b.png", {
        targetColor: undefined,
        threshold: 8,
        featherRadius: undefined,
      }),
    );
  });

  it("shows the original image when transparency is off", () => {
    retain.mockClear();
    const { result } = renderHook(() =>
      useTransparentImage("/img/c.png", false),
    );

    expect(result.current.url).toBe("/img/c.png");
    expect(retain).not.toHaveBeenCalled();
  });
});
