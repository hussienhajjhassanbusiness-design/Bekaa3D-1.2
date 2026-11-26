import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { useVerifyEmail } from "./useVerifyEmail";

// FVS-002-IMPLEMENTATION-PLAN.md §1 rows 1/8/9/10 (confirmed at BATCH 2):
// exact path/body, 204 success with no body required. Mocks apiClient.post
// — no real network/proxy/backend is ever contacted.

function createWrapper() {
  const queryClient = new QueryClient();
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

function httpError(status: number): ApiError {
  return { kind: "http", status, message: "Something went wrong. Please try again.", raw: { status } };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useVerifyEmail", () => {
  it("calls apiClient.post with the exact path and body, no trailing slash", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(undefined);
    const { result } = renderHook(() => useVerifyEmail(), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.mutateAsync({ token: "a".repeat(43) });
    });

    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(postSpy).toHaveBeenCalledWith("/api/v1/auth/verify-email", { token: "a".repeat(43) });
  });

  it("treats a 204 (undefined-resolving) response as success, requiring no response body", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue(undefined);
    const { result } = renderHook(() => useVerifyEmail(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ token: "a".repeat(43) })).resolves.toBeUndefined();
    });
  });

  it("never retries automatically", async () => {
    vi.useFakeTimers();
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(httpError(400));
    const { result } = renderHook(() => useVerifyEmail(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ token: "a".repeat(43) })).rejects.toBeDefined();
    });

    // Advance past TanStack Query's default backoff window — a dropped
    // `retry: false` would surface here as a second call.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(postSpy).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("surfaces the ApiError unchanged (400/410/429/network/timeout all pass through as-is)", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(httpError(410));
    const { result } = renderHook(() => useVerifyEmail(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ token: "a".repeat(43) })).rejects.toMatchObject({ status: 410 });
    });
  });
});
