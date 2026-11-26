import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { usePasswordResetConfirm } from "./usePasswordResetConfirm";

// Phase 2 auth/account batch — confirmed contract (openapi.json):
// POST /api/v1/auth/password-reset/confirm, body {token, new_password},
// 204 (no body) on success; public (no cookie, no CSRF header) —
// BACKEND-RESPONSE.md P2-6. A successful reset revokes every session and
// does NOT log the user in — this hook performs no session-query
// invalidation and no navigation of its own.

function createWrapper() {
  const queryClient = new QueryClient();
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

function networkError(): ApiError {
  return { kind: "network", message: "We couldn't reach the server.", raw: undefined };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("usePasswordResetConfirm", () => {
  it("calls apiClient.post with the exact path and body, with no csrf option", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(undefined);
    const { result } = renderHook(() => usePasswordResetConfirm(), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.mutateAsync({ token: "abc123", new_password: "newpassword1" });
    });

    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(postSpy).toHaveBeenCalledWith("/api/v1/auth/password-reset/confirm", {
      token: "abc123",
      new_password: "newpassword1",
    });
  });

  it("surfaces a 410 (expired token) failure unchanged", async () => {
    const expired: ApiError = { kind: "http", status: 410, message: "An unexpected error occurred.", raw: {} };
    vi.spyOn(apiClient, "post").mockRejectedValue(expired);
    const { result } = renderHook(() => usePasswordResetConfirm(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(
        result.current.mutateAsync({ token: "expired-token", new_password: "newpassword1" })
      ).rejects.toMatchObject({ kind: "http", status: 410 });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("surfaces a 400 (token unknown/used/account unusable) failure unchanged", async () => {
    const invalid: ApiError = { kind: "http", status: 400, message: "An unexpected error occurred.", raw: {} };
    vi.spyOn(apiClient, "post").mockRejectedValue(invalid);
    const { result } = renderHook(() => usePasswordResetConfirm(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(
        result.current.mutateAsync({ token: "used-token", new_password: "newpassword1" })
      ).rejects.toMatchObject({ kind: "http", status: 400 });
    });
  });

  it("never retries automatically", async () => {
    vi.useFakeTimers();
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(networkError());
    const { result } = renderHook(() => usePasswordResetConfirm(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(
        result.current.mutateAsync({ token: "abc123", new_password: "newpassword1" })
      ).rejects.toBeDefined();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(postSpy).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
