// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  apiErrorFromResponse,
  extractErrorCode,
  extractErrorMessage,
  jsonInit,
  requestJson,
} from "./http";

function fakeResponse(
  status: number,
  body: unknown,
  statusText = "",
): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    json: async () => {
      if (body instanceof Error) throw body;
      return body;
    },
  } as unknown as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("extractErrorMessage", () => {
  it("returns detail string as is", () => {
    expect(extractErrorMessage({ detail: "boom" }, "fb")).toBe("boom");
  });

  it("prefers detail.message, then nested detail.detail", () => {
    expect(
      extractErrorMessage({ detail: { message: "m", code: "c" } }, "fb"),
    ).toBe("m");
    expect(extractErrorMessage({ detail: { detail: "inner" } }, "fb")).toBe(
      "inner",
    );
  });

  it("joins validation error messages", () => {
    expect(
      extractErrorMessage(
        { detail: [{ msg: "a" }, { msg: "b" }, { other: 1 }] },
        "fb",
      ),
    ).toBe("a / b");
  });

  it("falls back when detail is missing or unusable", () => {
    expect(extractErrorMessage(null, "fb")).toBe("fb");
    expect(extractErrorMessage({ detail: { code: "x" } }, "fb")).toBe("fb");
    expect(extractErrorMessage({ detail: [] }, "fb")).toBe("fb");
  });
});

describe("extractErrorCode", () => {
  it("reads detail.code only when it is a string", () => {
    expect(extractErrorCode({ detail: { code: "memory_empty" } })).toBe(
      "memory_empty",
    );
    expect(extractErrorCode({ detail: { code: 3 } })).toBeNull();
    expect(extractErrorCode({ detail: "plain" })).toBeNull();
    expect(extractErrorCode(undefined)).toBeNull();
  });
});

describe("requestJson", () => {
  it("returns parsed JSON and passes init through", async () => {
    const fetchMock = vi.fn(async () => fakeResponse(200, { ok: 1 }));
    vi.stubGlobal("fetch", fetchMock);
    const init = jsonInit("POST", { a: 1 });

    await expect(requestJson<{ ok: number }>("/x", init)).resolves.toEqual({
      ok: 1,
    });
    expect(fetchMock).toHaveBeenCalledWith("/x", init);
    expect(init.body).toBe('{"a":1}');
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
  });

  it("returns undefined for 204", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => fakeResponse(204, new Error("no body"))),
    );
    await expect(requestJson("/x")).resolves.toBeUndefined();
  });

  it("throws ApiError with message, status and code", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        fakeResponse(422, { detail: { message: "bad", code: "invalid" } }),
      ),
    );
    const err = await requestJson("/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).message).toBe("bad");
    expect((err as ApiError).status).toBe(422);
    expect((err as ApiError).code).toBe("invalid");
  });

  it("uses fallbackMessage, then statusText, when detail is absent", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => fakeResponse(500, new Error("not json"), "Server")),
    );
    const withFallback = (await requestJson("/x", undefined, {
      fallbackMessage: "custom",
    }).catch((e: unknown) => e)) as ApiError;
    expect(withFallback.message).toBe("custom");

    const withoutFallback = (await requestJson("/x").catch(
      (e: unknown) => e,
    )) as ApiError;
    expect(withoutFallback.message).toBe("Server");
  });
});

describe("apiErrorFromResponse", () => {
  it("builds ApiError from a non-ok response", async () => {
    const err = await apiErrorFromResponse(
      fakeResponse(404, { detail: "missing" }),
    );
    expect(err.status).toBe(404);
    expect(err.message).toBe("missing");
    expect(err.code).toBeNull();
  });
});

describe("jsonInit", () => {
  it("omits body when undefined", () => {
    expect(jsonInit("DELETE")).toEqual({
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: undefined,
    });
  });
});
