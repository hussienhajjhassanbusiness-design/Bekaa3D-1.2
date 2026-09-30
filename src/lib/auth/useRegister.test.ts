import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { useRegister } from "./useRegister";

// FVS-002-IMPLEMENTATION-PLAN.md §1 rows 1/2/5/6/15 (confirmed at BATCH 2):
// exact path, exact request body, HTTP 202 success, `{ message }` success
// body (never read), no auth/session state. Mocks apiClient.post (the
// correct transport boundary, matching useReadiness's own apiClient.get
// mocking precedent) — no real network/proxy/backend is ever contacted.

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

describe("useRegister", () => {
  it("calls apiClient.post with the exact path and body, no trailing slash", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue({ message: "check your email" });
    const { result } = renderHook(() => useRegister(), { wrapper: createWrapper() });

    await act(async () => {
      await result.current.mutateAsync({ email: "ada@example.com", password: "password123" });
    });

    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(postSpy).toHaveBeenCalledWith("/api/v1/auth/register", {
      email: "ada@example.com",
      password: "password123",
    });
  });

  it("resolves successfully regardless of whether the mocked response implies a new or an existing account (enumeration-safety at the transport boundary)", async () => {
    const postSpy = vi
      .spyOn(apiClient, "post")
      .mockResolvedValueOnce({ message: "new account" })
      .mockResolvedValueOnce({ message: "existing account" });

    const { result: resultA } = renderHook(() => useRegister(), { wrapper: createWrapper() });
    await act(async () => {
      await expect(resultA.current.mutateAsync({ email: "new@example.com", password: "password123" })).resolves.toBeDefined();
    });

    const { result: resultB } = renderHook(() => useRegister(), { wrapper: createWrapper() });
    await act(async () => {
      await expect(
        resultB.current.mutateAsync({ email: "existing@example.com", password: "password123" })
      ).resolves.toBeDefined();
    });

    expect(postSpy).toHaveBeenCalledTimes(2);
  });

  it("surfaces a network failure as ApiError.kind: 'network'", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(networkError());
    const { result } = renderHook(() => useRegister(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ email: "ada@example.com", password: "password123" })).rejects.toMatchObject({
        kind: "network",
      });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("never retries automatically — a rejected mutation is not retried by TanStack Query", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(networkError());
    const { result } = renderHook(() => useRegister(), { wrapper: createWrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync({ email: "ada@example.com", password: "password123" })).rejects.toBeDefined();
    });

    // A single failed call, with no automatic retry attempts appended.
    expect(postSpy).toHaveBeenCalledTimes(1);
  });
});
