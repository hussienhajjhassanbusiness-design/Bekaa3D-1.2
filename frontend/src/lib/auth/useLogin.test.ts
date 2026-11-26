import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { useLogin } from "./useLogin";
import * as refreshSessionModule from "./refreshSession";

// FVS-003-IMPLEMENTATION-PLAN.md §2 rows 2/5/5b/6/8/9/9b (confirmed BATCH
// 3B) — login's two disjoint success shapes (200 session / 202 MFA
// challenge) are discriminated by body shape, never by trusting "any 2xx."
// Calls apiClient directly — never authenticatedRequest, never triggers a
// refresh on any failure (login itself is excluded from the refresh
// wrapper, per the plan's own §6 exclusion rule).

function createWrapper() {
  const queryClient = new QueryClient();
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

const SESSION_BODY = {
  user_id: "u-1",
  email: "ada@example.com",
  role: "customer",
  email_verified: true,
  session_expires_at: "2026-01-01T00:15:00Z",
};

const MFA_BODY = {
  challenge_id: "chal-123",
  expires_in_seconds: 300,
};

function httpError(status: number, code?: string, extra: Record<string, unknown> = {}): ApiError {
  return { kind: "http", status, code, message: "x", raw: undefined, ...extra };
}
function networkError(): ApiError {
  return { kind: "network", message: "x", raw: undefined };
}
function timeoutError(): ApiError {
  return { kind: "timeout", message: "x", raw: undefined };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useLogin", () => {
  it("calls the exact path and body, no trailing slash, with no CSRF header option", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(SESSION_BODY);
    const { result } = renderHook(() => useLogin(), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.mutateAsync({ email: "ada@example.com", password: "password123" });
    });

    expect(postSpy).toHaveBeenCalledTimes(1);
    const [path, body, options] = postSpy.mock.calls[0] as [string, unknown, Record<string, unknown> | undefined];
    expect(path).toBe("/api/v1/auth/login");
    expect(path.endsWith("/")).toBe(false);
    expect(body).toEqual({ email: "ada@example.com", password: "password123" });
    expect(options?.csrf).toBeUndefined();
  });

  it("retry: false is configured — a rejection is never retried, even past TanStack's default backoff window", async () => {
    vi.useFakeTimers();
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(httpError(401, "INVALID_CREDENTIALS"));
    const { result } = renderHook(() => useLogin(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ email: "a@example.com", password: "x" })).rejects.toBeDefined();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(postSpy).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("a 200 session response resolves a discriminated 'session' result with the mapped user data", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue(SESSION_BODY);
    const { result } = renderHook(() => useLogin(), { wrapper: createWrapper() });

    const outcome = await act(async () =>
      result.current.mutateAsync({ email: "ada@example.com", password: "password123" })
    );

    expect(outcome).toEqual({
      kind: "session",
      data: SESSION_BODY,
    });
  });

  it("a 202 MFA-challenge response resolves a discriminated 'mfaChallenge' result, distinguishable without inspecting raw response diagnostics", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue(MFA_BODY);
    const { result } = renderHook(() => useLogin(), { wrapper: createWrapper() });

    const outcome = await act(async () =>
      result.current.mutateAsync({ email: "admin@example.com", password: "password123" })
    );

    expect(outcome).toEqual({ kind: "mfaChallenge", data: MFA_BODY });
    expect(outcome.kind).not.toBe("session");
  });

  it("a 401 INVALID_CREDENTIALS failure passes through unchanged", async () => {
    const error = httpError(401, "INVALID_CREDENTIALS");
    vi.spyOn(apiClient, "post").mockRejectedValue(error);
    const { result } = renderHook(() => useLogin(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ email: "a@example.com", password: "x" })).rejects.toBe(error);
    });
  });

  it("a 403 ACCOUNT_DISABLED failure passes through unchanged", async () => {
    const error = httpError(403, "ACCOUNT_DISABLED");
    vi.spyOn(apiClient, "post").mockRejectedValue(error);
    const { result } = renderHook(() => useLogin(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ email: "a@example.com", password: "x" })).rejects.toBe(error);
    });
  });

  it("a 429 RATE_LIMITED failure preserves retryAfterSeconds", async () => {
    const error = httpError(429, "RATE_LIMITED", { retryAfterSeconds: 120 });
    vi.spyOn(apiClient, "post").mockRejectedValue(error);
    const { result } = renderHook(() => useLogin(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ email: "a@example.com", password: "x" })).rejects.toMatchObject({
        code: "RATE_LIMITED",
        retryAfterSeconds: 120,
      });
    });
  });

  it("a network failure passes through unchanged", async () => {
    const error = networkError();
    vi.spyOn(apiClient, "post").mockRejectedValue(error);
    const { result } = renderHook(() => useLogin(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ email: "a@example.com", password: "x" })).rejects.toBe(error);
    });
  });

  it("a timeout failure passes through unchanged", async () => {
    const error = timeoutError();
    vi.spyOn(apiClient, "post").mockRejectedValue(error);
    const { result } = renderHook(() => useLogin(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ email: "a@example.com", password: "x" })).rejects.toBe(error);
    });
  });

  it("never triggers a refresh on login failure (refreshSession is never called)", async () => {
    const refreshSpy = vi.spyOn(refreshSessionModule, "refreshSession");
    vi.spyOn(apiClient, "post").mockRejectedValue(httpError(401, "INVALID_CREDENTIALS"));
    const { result } = renderHook(() => useLogin(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ email: "a@example.com", password: "x" })).rejects.toBeDefined();
    });

    expect(refreshSpy).not.toHaveBeenCalled();
  });
});
