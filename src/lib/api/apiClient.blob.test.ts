import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "./apiClient";

afterEach(() => vi.restoreAllMocks());

describe("apiClient.getBlob", () => {
  it("returns the bytes and the RFC 6266 filename* (preferred over the ASCII fallback)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(new Uint8Array([1, 2, 3]), {
        status: 200,
        headers: { "Content-Disposition": "attachment; filename=\"_.png\"; filename*=UTF-8''%D8%B1%D8%B3%D9%85.png" },
      })
    );
    const result = await apiClient.getBlob("/api/v1/admin/x/download");
    expect(result.filename).toBe("رسم.png");
    expect(result.blob.size).toBe(3);
  });

  it("falls back to the quoted filename, or null without the header", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response("x", { status: 200, headers: { "Content-Disposition": 'attachment; filename="sketch.jpg"' } }))
      .mockResolvedValueOnce(new Response("x", { status: 200 }));
    expect((await apiClient.getBlob("/api/v1/a")).filename).toBe("sketch.jpg");
    expect((await apiClient.getBlob("/api/v1/a")).filename).toBeNull();
  });

  it("throws a parsed ApiError with the status on a Problem response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ type: "about:blank", title: "t", status: 404, detail: "d", code: "NOT_FOUND", errors: [] }), {
        status: 404,
        headers: { "Content-Type": "application/problem+json" },
      })
    );
    await expect(apiClient.getBlob("/api/v1/a")).rejects.toMatchObject({ kind: "http", status: 404, code: "NOT_FOUND" });
  });

  it("refuses a non-/api/ path and maps a failed fetch to a network error", async () => {
    await expect(apiClient.getBlob("https://evil.example/x")).rejects.toThrow();
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("offline"));
    await expect(apiClient.getBlob("/api/v1/a")).rejects.toMatchObject({ kind: "network" });
  });
});
