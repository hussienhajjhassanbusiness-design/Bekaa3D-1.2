import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { usePasswordResetRequest } from "./usePasswordResetRequest";

// Phase 2 auth/account batch — confirmed contract (openapi.json):
// POST /api/v1/auth/password-reset/request, body {email}, 202 always,
// public (no cookie, no CSRF header) — BACKEND-RESPONSE.md P2-6.

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

describe("usePasswordResetRequest", () => {
  it("calls apiClient.post with the exact path and body, with no csrf option", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue({ message: "ok" });
    const { result } = renderHook(() => usePasswordResetRequest(), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.mutateAsync({ email: "ada@example.com", captcha_token: "tok-1" });
    });

    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(postSpy).toHaveBeenCalledWith("/api/v1/auth/password-reset/request", { email: "ada@example.com", captcha_token: "tok-1" });
  });

  it("resolves successfully regardless of whether the account exists (enumeration-safety at the transport boundary)", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue({ message: "If an account exists..." });
    const { result } = renderHook(() => usePasswordResetRequest(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ email: "unknown@example.com", captcha_token: "tok-1" })).resolves.toBeDefined();
    });
  });

  it("surfaces a network failure as ApiError.kind: 'network'", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(networkError());
    const { result } = renderHook(() => usePasswordResetRequest(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ email: "ada@example.com", captcha_token: "tok-1" })).rejects.toMatchObject({
        kind: "network",
      });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("never retries automatically", async () => {
    vi.useFakeTimers();
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(networkError());
    const { result } = renderHook(() => usePasswordResetRequest(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ email: "ada@example.com", captcha_token: "tok-1" })).rejects.toBeDefined();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(postSpy).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
