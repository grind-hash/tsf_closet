import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useTransparentImages } from "./useTransparentImages";

const handles = vi.hoisted(() => ({ released: [] as string[] }));
const retain = vi.hoisted(() =>
  vi.fn((src: string) => ({
    url: src.includes("broken")
      ? Promise.reject(new Error("decode failed"))
      : Promise.resolve(`blob:${src}`),
    release: () => handles.released.push(src),
  })),
);

vi.mock("../utils/imageAlpha", () => ({
  retainTransparentImage: retain,
}));

const OPTIONS = { targetColor: null, threshold: 12 };

describe("useTransparentImages", () => {
  it("maps each source once and ignores empty entries", async () => {
    const sources = ["/a.png", null, "/b.png", "/a.png"];
    const { result } = renderHook(() => useTransparentImages(sources, OPTIONS));

    await waitFor(() =>
      expect(result.current).toEqual({
        "/a.png": "blob:/a.png",
        "/b.png": "blob:/b.png",
      }),
    );
    expect(retain).toHaveBeenCalledTimes(2);
    expect(retain).toHaveBeenCalledWith("/a.png", {
      targetColor: null,
      threshold: 12,
      featherRadius: undefined,
    });
  });

  it("falls back to the original url when processing fails", async () => {
    const sources = ["/broken.png"];
    const { result } = renderHook(() => useTransparentImages(sources, OPTIONS));

    await waitFor(() =>
      expect(result.current).toEqual({ "/broken.png": "/broken.png" }),
    );
  });

  it("releases images that leave the list and drops their mapping", async () => {
    handles.released.length = 0;
    const { result, rerender } = renderHook(
      ({ sources }) => useTransparentImages(sources, OPTIONS),
      { initialProps: { sources: ["/c.png", "/d.png"] } },
    );
    await waitFor(() => expect(Object.keys(result.current)).toHaveLength(2));

    rerender({ sources: ["/d.png"] });

    await waitFor(() =>
      expect(result.current).toEqual({ "/d.png": "blob:/d.png" }),
    );
    expect(handles.released).toContain("/c.png");
  });
});
