import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { refreshSession, REFRESH_LOCK_NAME } from "./refreshSession";

// FVS-003-IMPLEMENTATION-PLAN.md §7 (confirmed BATCH 3A) — the real,
// auth-domain refresh coordinator: same-tab single-flight (reusing T06's
// unmodified generic primitive) layered with cross-tab mutual exclusion via
// the native Web Locks API. `navigator.locks` is stubbed with an explicit
// test double throughout (real cross-tab behavior cannot be exercised
// within one Vitest module anyway — two sequential calls after the first
// settles is how "a second contender arrives later" is simulated here).

function httpError(status: number, code?: string): ApiError {
  return { kind: "http", status, code, message: "x", raw: undefined };
}

function createLocksDouble() {
  const acquiredNames: string[] = [];
  return {
    acquiredNames,
    request: vi.fn(async (name: string, callback: () => Promise<unknown>) => {
      acquiredNames.push(name);
      return callback();
    }),
  };
}

let originalLocks: unknown;

beforeEach(() => {
  originalLocks = (navigator as unknown as { locks?: unknown }).locks;
});

afterEach(() => {
  vi.restoreAllMocks();
  Object.defineProperty(navigator, "locks", { value: originalLocks, configurable: true });
});

describe("refreshSession", () => {
  it("one refresh call succeeds (204, no body)", async () => {
    const locks = createLocksDouble();
    Object.defineProperty(navigator, "locks", { value: locks, configurable: true });
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(undefined);

    const result = await refreshSession();

    expect(result).toBe(true);
    expect(postSpy).toHaveBeenCalledTimes(1);
  });

  it("five same-tab concurrent callers result in exactly one POST /refresh", async () => {
    const locks = createLocksDouble();
    Object.defineProperty(navigator, "locks", { value: locks, configurable: true });
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(undefined);

    await Promise.all([refreshSession(), refreshSession(), refreshSession(), refreshSession(), refreshSession()]);

    expect(postSpy).toHaveBeenCalledTimes(1);
  });

  it("calls the exact refresh path, no trailing slash, no body", async () => {
    const locks = createLocksDouble();
    Object.defineProperty(navigator, "locks", { value: locks, configurable: true });
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(undefined);

    await refreshSession();

    expect(postSpy).toHaveBeenCalledWith("/api/v1/auth/refresh", undefined, expect.objectContaining({ csrf: true }));
    const [path] = postSpy.mock.calls[0] as [string, ...unknown[]];
    expect(path.endsWith("/")).toBe(false);
  });

  it("sends the request with CSRF enabled (the apiClient { csrf: true } opt-in)", async () => {
    const locks = createLocksDouble();
    Object.defineProperty(navigator, "locks", { value: locks, configurable: true });
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(undefined);

    await refreshSession();

    const [, , options] = postSpy.mock.calls[0] as [string, unknown, { csrf?: boolean }];
    expect(options.csrf).toBe(true);
  });

  it("a 401 refresh failure resolves false, not a thrown rejection", async () => {
    const locks = createLocksDouble();
    Object.defineProperty(navigator, "locks", { value: locks, configurable: true });
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    vi.spyOn(apiClient, "post").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));

    await expect(refreshSession()).resolves.toBe(false);
  });

  it("a 403 CSRF_INVALID refresh failure resolves false", async () => {
    const locks = createLocksDouble();
    Object.defineProperty(navigator, "locks", { value: locks, configurable: true });
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    vi.spyOn(apiClient, "post").mockRejectedValue(httpError(403, "CSRF_INVALID"));

    await expect(refreshSession()).resolves.toBe(false);
  });

  it("a 429 RATE_LIMITED refresh failure resolves false, with no automatic retry of the refresh call itself", async () => {
    const locks = createLocksDouble();
    Object.defineProperty(navigator, "locks", { value: locks, configurable: true });
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(httpError(429, "RATE_LIMITED"));

    await expect(refreshSession()).resolves.toBe(false);
    expect(postSpy).toHaveBeenCalledTimes(1);
  });

  it("the same-tab slot clears after a success, allowing a later independent call to run again", async () => {
    const locks = createLocksDouble();
    Object.defineProperty(navigator, "locks", { value: locks, configurable: true });
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(undefined);

    await refreshSession();
    await refreshSession();

    expect(postSpy).toHaveBeenCalledTimes(2);
  });

  it("the same-tab slot clears after a failure too, allowing a later independent call to run again", async () => {
    const locks = createLocksDouble();
    Object.defineProperty(navigator, "locks", { value: locks, configurable: true });
    const getSpy = vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    const postSpy = vi
      .spyOn(apiClient, "post")
      .mockRejectedValueOnce(httpError(401, "AUTH_REQUIRED"))
      .mockResolvedValueOnce(undefined);

    await expect(refreshSession()).resolves.toBe(false);
    getSpy.mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    await expect(refreshSession()).resolves.toBe(true);

    expect(postSpy).toHaveBeenCalledTimes(2);
  });

  it("acquires the stable, named Web Lock before refreshing", async () => {
    const locks = createLocksDouble();
    Object.defineProperty(navigator, "locks", { value: locks, configurable: true });
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    vi.spyOn(apiClient, "post").mockResolvedValue(undefined);

    await refreshSession();

    expect(locks.request).toHaveBeenCalledTimes(1);
    expect(locks.acquiredNames).toEqual([REFRESH_LOCK_NAME]);
  });

  it("re-checks the session (GET /me) inside the lock before deciding whether to refresh", async () => {
    const locks = createLocksDouble();
    Object.defineProperty(navigator, "locks", { value: locks, configurable: true });
    const getSpy = vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(undefined);

    await refreshSession();

    expect(getSpy).toHaveBeenCalledWith("/api/v1/me");
    // The recheck happens before the actual refresh call, within the lock.
    const [getOrder] = getSpy.mock.invocationCallOrder;
    const [postOrder] = postSpy.mock.invocationCallOrder;
    expect(getOrder).toBeDefined();
    expect(postOrder).toBeDefined();
    expect(getOrder).toBeLessThan(postOrder as number);
  });

  it("a second contender who re-checks and finds the session already valid does not refresh again (avoids a duplicate sequential refresh)", async () => {
    const locks = createLocksDouble();
    Object.defineProperty(navigator, "locks", { value: locks, configurable: true });
    const getSpy = vi.spyOn(apiClient, "get");
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(undefined);

    // Tab A: session invalid, refreshes for real.
    getSpy.mockRejectedValueOnce(httpError(401, "AUTH_REQUIRED"));
    const resultA = await refreshSession();

    // Tab B (simulated as a later, independent call once the same-tab slot
    // has cleared): re-checks /me and finds it now valid, since "Tab A"
    // already refreshed — must NOT call refresh a second time.
    getSpy.mockResolvedValueOnce({ id: "u1", email: "a@example.com" });
    const resultB = await refreshSession();

    expect(resultA).toBe(true);
    expect(resultB).toBe(true);
    expect(postSpy).toHaveBeenCalledTimes(1);
  });

  it("falls back to same-tab-only protection (no throw) when Web Locks is unsupported", async () => {
    Object.defineProperty(navigator, "locks", { value: undefined, configurable: true });
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(undefined);

    await expect(refreshSession()).resolves.toBe(true);
    expect(postSpy).toHaveBeenCalledTimes(1);
  });

  it("does not recurse — refreshSession never calls itself or re-enters authenticatedRequest", async () => {
    const locks = createLocksDouble();
    Object.defineProperty(navigator, "locks", { value: locks, configurable: true });
    const getSpy = vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));

    await refreshSession();

    // Exactly one /me recheck and one /refresh attempt — a recursive
    // implementation would show additional, unexplained calls here.
    expect(getSpy).toHaveBeenCalledTimes(1);
    expect(postSpy).toHaveBeenCalledTimes(1);
  });
});
