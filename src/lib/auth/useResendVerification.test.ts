import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { useResendVerification } from "./useResendVerification";

// FVS-002-IMPLEMENTATION-PLAN.md §1 rows 1/11/12 (confirmed at BATCH 2):
// exact path/body, 202 success, enumeration-safe regardless of mocked
// account existence. Mocks apiClient.post — no real network/backend hit.

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

describe("useResendVerification", () => {
  it("calls apiClient.post with the exact path and body, no trailing slash", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue({ message: "sent" });
    const { result } = renderHook(() => useResendVerification(), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.mutateAsync({ email: "ada@example.com", captcha_token: "tok-1" });
    });

    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(postSpy).toHaveBeenCalledWith("/api/v1/auth/resend-verification", { email: "ada@example.com", captcha_token: "tok-1" });
  });

  it("resolves successfully regardless of whether the mocked response implies the account exists or not", async () => {
    const postSpy = vi
      .spyOn(apiClient, "post")
      .mockResolvedValueOnce({ message: "existing account" })
      .mockResolvedValueOnce({ message: "no such account" });

    const { result: resultA } = renderHook(() => useResendVerification(), { wrapper: createWrapper() });
    await act(async () => {
      await expect(resultA.current.mutateAsync({ email: "existing@example.com", captcha_token: "tok-1" })).resolves.toBeDefined();
    });

    const { result: resultB } = renderHook(() => useResendVerification(), { wrapper: createWrapper() });
    await act(async () => {
      await expect(resultB.current.mutateAsync({ email: "missing@example.com", captcha_token: "tok-1" })).resolves.toBeDefined();
    });

    expect(postSpy).toHaveBeenCalledTimes(2);
  });

  it("never retries automatically", async () => {
    vi.useFakeTimers();
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(networkError());
    const { result } = renderHook(() => useResendVerification(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ email: "ada@example.com", captcha_token: "tok-1" })).rejects.toBeDefined();
    });

    // Advance past TanStack Query's default backoff window — a dropped
    // `retry: false` would surface here as a second call.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(postSpy).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
