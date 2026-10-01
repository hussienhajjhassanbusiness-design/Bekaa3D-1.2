import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { authenticatedRequest } from "./authenticatedRequest";

// FVS-003-IMPLEMENTATION-PLAN.md §6/§8 (confirmed BATCH 3A) — only
// `401 AUTH_REQUIRED` is refreshable; everything else (MFA_REQUIRED, 403,
// 429, network, timeout, 500) passes through unchanged. Backend-confirmed
// replay safety means both reads and writes may be retried once after a
// successful refresh — no GET/POST distinction in this wrapper.
//
// Tests use the REAL refreshSession module (mocking apiClient underneath,
// same technique as refreshSession.test.ts) so the concurrent-dedup tests
// exercise genuine end-to-end behavior, not a mocked stand-in.

function httpError(status: number, code?: string): ApiError {
  return { kind: "http", status, code, message: "x", raw: undefined };
}
function networkError(): ApiError {
  return { kind: "network", message: "x", raw: undefined };
}
function timeoutError(): ApiError {
  return { kind: "timeout", message: "x", raw: undefined };
}

function createLocksDouble() {
  return {
    request: vi.fn(async (_name: string, callback: () => Promise<unknown>) => callback()),
  };
}

let originalLocks: unknown;

beforeEach(() => {
  originalLocks = (navigator as unknown as { locks?: unknown }).locks;
  Object.defineProperty(navigator, "locks", { value: createLocksDouble(), configurable: true });
});

afterEach(() => {
  vi.restoreAllMocks();
  Object.defineProperty(navigator, "locks", { value: originalLocks, configurable: true });
});

describe("authenticatedRequest", () => {
  it("401 AUTH_REQUIRED triggers exactly one refresh, then retries the original call once, and resolves with the retry's value", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED")); // /me recheck inside refresh
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(undefined); // refresh succeeds

    const call = vi.fn().mockRejectedValueOnce(httpError(401, "AUTH_REQUIRED")).mockResolvedValueOnce("retried-value");

    const result = await authenticatedRequest(call);

    expect(result).toBe("retried-value");
    expect(call).toHaveBeenCalledTimes(2);
    expect(postSpy).toHaveBeenCalledTimes(1);
  });

  it("if refresh itself fails, the original call is never retried — the original AUTH_REQUIRED error surfaces", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    vi.spyOn(apiClient, "post").mockRejectedValue(httpError(401, "AUTH_REQUIRED")); // refresh itself fails

    const originalError = httpError(401, "AUTH_REQUIRED");
    const call = vi.fn().mockRejectedValue(originalError);

    await expect(authenticatedRequest(call)).rejects.toBe(originalError);
    expect(call).toHaveBeenCalledTimes(1);
  });

  it("if the retried call also fails with AUTH_REQUIRED, it is surfaced without a second refresh attempt", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(undefined); // refresh succeeds once

    const retryError = httpError(401, "AUTH_REQUIRED");
    const call = vi.fn().mockRejectedValueOnce(httpError(401, "AUTH_REQUIRED")).mockRejectedValueOnce(retryError);

    await expect(authenticatedRequest(call)).rejects.toBe(retryError);
    expect(call).toHaveBeenCalledTimes(2);
    expect(postSpy).toHaveBeenCalledTimes(1);
  });

  it("401 MFA_REQUIRED never triggers a refresh — passes through unchanged", async () => {
    const postSpy = vi.spyOn(apiClient, "post");
    const error = httpError(401, "MFA_REQUIRED");
    const call = vi.fn().mockRejectedValue(error);

    await expect(authenticatedRequest(call)).rejects.toBe(error);
    expect(call).toHaveBeenCalledTimes(1);
    expect(postSpy).not.toHaveBeenCalled();
  });

  it("403 never triggers a refresh", async () => {
    const postSpy = vi.spyOn(apiClient, "post");
    const error = httpError(403, "CSRF_INVALID");
    const call = vi.fn().mockRejectedValue(error);

    await expect(authenticatedRequest(call)).rejects.toBe(error);
    expect(postSpy).not.toHaveBeenCalled();
  });

  it("429 never triggers a refresh", async () => {
    const postSpy = vi.spyOn(apiClient, "post");
    const error = httpError(429, "RATE_LIMITED");
    const call = vi.fn().mockRejectedValue(error);

    await expect(authenticatedRequest(call)).rejects.toBe(error);
    expect(postSpy).not.toHaveBeenCalled();
  });

  it("a network error never triggers a refresh", async () => {
    const postSpy = vi.spyOn(apiClient, "post");
    const error = networkError();
    const call = vi.fn().mockRejectedValue(error);

    await expect(authenticatedRequest(call)).rejects.toBe(error);
    expect(postSpy).not.toHaveBeenCalled();
  });

  it("a timeout error never triggers a refresh", async () => {
    const postSpy = vi.spyOn(apiClient, "post");
    const error = timeoutError();
    const call = vi.fn().mockRejectedValue(error);

    await expect(authenticatedRequest(call)).rejects.toBe(error);
    expect(postSpy).not.toHaveBeenCalled();
  });

  it("a 500 error never triggers a refresh", async () => {
    const postSpy = vi.spyOn(apiClient, "post");
    const error = httpError(500);
    const call = vi.fn().mockRejectedValue(error);

    await expect(authenticatedRequest(call)).rejects.toBe(error);
    expect(postSpy).not.toHaveBeenCalled();
  });

  it("concurrent AUTH_REQUIRED requests dedupe correctly through the refresh layer — five concurrent original calls produce exactly one underlying refresh", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(undefined);

    const call = vi
      .fn()
      .mockRejectedValueOnce(httpError(401, "AUTH_REQUIRED"))
      .mockRejectedValueOnce(httpError(401, "AUTH_REQUIRED"))
      .mockRejectedValueOnce(httpError(401, "AUTH_REQUIRED"))
      .mockRejectedValueOnce(httpError(401, "AUTH_REQUIRED"))
      .mockRejectedValueOnce(httpError(401, "AUTH_REQUIRED"))
      .mockResolvedValue("ok");

    const results = await Promise.all([
      authenticatedRequest(call),
      authenticatedRequest(call),
      authenticatedRequest(call),
      authenticatedRequest(call),
      authenticatedRequest(call),
    ]);

    expect(results).toEqual(["ok", "ok", "ok", "ok", "ok"]);
    expect(postSpy).toHaveBeenCalledTimes(1);
  });

  it("a write (non-GET) callback is retried once after a successful refresh, same as a read", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    vi.spyOn(apiClient, "post").mockResolvedValue(undefined);

    const writeCall = vi
      .fn()
      .mockRejectedValueOnce(httpError(401, "AUTH_REQUIRED"))
      .mockResolvedValueOnce({ created: true });

    const result = await authenticatedRequest(() => writeCall() as Promise<{ created: boolean }>);

    expect(result).toEqual({ created: true });
    expect(writeCall).toHaveBeenCalledTimes(2);
  });
});
