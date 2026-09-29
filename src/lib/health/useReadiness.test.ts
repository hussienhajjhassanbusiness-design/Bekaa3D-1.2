import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { useReadiness, getReadinessQueryOptions } from "./useReadiness";

// FVS-001-IMPLEMENTATION-PLAN.md §16's state matrix, translated directly —
// every row gets its own test. Mocks apiClient.get (the correct boundary per
// the T13a task prompt) so no real network/proxy/backend is ever contacted.
// Each test gets its own fresh QueryClient so cache/retry state never leaks
// between tests.

function createWrapper() {
  const queryClient = new QueryClient();
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

function networkError(): ApiError {
  return { kind: "network", message: "We couldn't reach the server.", raw: undefined };
}

function timeoutError(): ApiError {
  return { kind: "timeout", message: "The server took too long to respond. Please try again.", raw: undefined };
}

function httpNotReadyError(): ApiError {
  return {
    kind: "http",
    status: 503,
    message: "Something went wrong. Please try again.",
    raw: { status: 503 },
  };
}

function malformedNonProblemError(): ApiError {
  // T09's actual output for a non-2xx response with a malformed/non-JSON
  // body: kind "parse", status deliberately absent (T09 never attaches a
  // status for this kind — see apiClient.ts's own contract comment).
  return {
    kind: "parse",
    message: "Something went wrong. Please try again.",
    raw: "<html><body>Bad Gateway</body></html>",
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useReadiness", () => {
  it("§16 row: Healthy (2xx) → ready", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ irrelevant: "body content is never read" });

    const { result } = renderHook(() => useReadiness(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.state).toBe("ready");
  });

  it("§16 row: Malformed response body, 2xx case → still ready (a malformed/empty successful body never blocks readiness)", async () => {
    // Matches apiClient.ts's own real behavior: a 2xx response with an
    // empty/unparseable body resolves `undefined`, not an ApiError.
    vi.spyOn(apiClient, "get").mockResolvedValue(undefined);

    const { result } = renderHook(() => useReadiness(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.state).toBe("ready");
  });

  it(
    "§16 row: Not ready (non-2xx from a reachable server, well-formed problem body) → not-ready",
    async () => {
      vi.useFakeTimers();
      vi.spyOn(apiClient, "get").mockRejectedValue(httpNotReadyError());

      const { result } = renderHook(() => useReadiness(), { wrapper: createWrapper() });
      await vi.advanceTimersByTimeAsync(10_000);

      expect(result.current.isLoading).toBe(false);
      expect(result.current.state).toBe("not-ready");
      vi.useRealTimers();
    }
  );

  it(
    "§16 row: Malformed response body, non-2xx case (ApiError.kind: 'parse') → still not-ready — a malformed body never blocks ready/not-ready determination",
    async () => {
      vi.useFakeTimers();
      vi.spyOn(apiClient, "get").mockRejectedValue(malformedNonProblemError());

      const { result } = renderHook(() => useReadiness(), { wrapper: createWrapper() });
      await vi.advanceTimersByTimeAsync(10_000);

      expect(result.current.isLoading).toBe(false);
      expect(result.current.state).toBe("not-ready");
      vi.useRealTimers();
    }
  );

  it("§16 row: Unreachable (ApiError.kind: 'network') → unreachable", async () => {
    vi.useFakeTimers();
    vi.spyOn(apiClient, "get").mockRejectedValue(networkError());

    const { result } = renderHook(() => useReadiness(), { wrapper: createWrapper() });
    await vi.advanceTimersByTimeAsync(10_000);

    expect(result.current.isLoading).toBe(false);
    expect(result.current.state).toBe("unreachable");
    vi.useRealTimers();
  });

  it("§16 row: Timeout (ApiError.kind: 'timeout') → timeout", async () => {
    vi.useFakeTimers();
    vi.spyOn(apiClient, "get").mockRejectedValue(timeoutError());

    const { result } = renderHook(() => useReadiness(), { wrapper: createWrapper() });
    await vi.advanceTimersByTimeAsync(10_000);

    expect(result.current.isLoading).toBe(false);
    expect(result.current.state).toBe("timeout");
    vi.useRealTimers();
  });

  it("distinguishes the initial loading state (no result yet) from a settled 'not-ready' result — never conflates the two", async () => {
    vi.useFakeTimers();
    let resolveGet: (value: unknown) => void;
    vi.spyOn(apiClient, "get").mockImplementation(
      () => new Promise((resolve) => { resolveGet = resolve; })
    );

    const { result } = renderHook(() => useReadiness(), { wrapper: createWrapper() });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.state).toBeUndefined();

    resolveGet!({});
    await vi.advanceTimersByTimeAsync(0);

    expect(result.current.isLoading).toBe(false);
    expect(result.current.state).toBe("ready");
    vi.useRealTimers();
  });

  it("calls exactly apiClient.get(\"/api/health/ready\") — never /health/ready, /api/health/live, or /health/live", async () => {
    const getSpy = vi.spyOn(apiClient, "get").mockResolvedValue(undefined);

    renderHook(() => useReadiness(), { wrapper: createWrapper() });

    await waitFor(() => expect(getSpy).toHaveBeenCalled());
    expect(getSpy).toHaveBeenCalledWith("/api/health/ready");
    expect(getSpy).not.toHaveBeenCalledWith("/health/ready");
    expect(getSpy).not.toHaveBeenCalledWith("/api/health/live");
    expect(getSpy).not.toHaveBeenCalledWith("/health/live");
  });

  it("configures the underlying query with the approved bounded settings (staleTime: 0, retry: 2, refetchInterval: 15000, refetchIntervalInBackground: false)", () => {
    const options = getReadinessQueryOptions();

    expect(options.queryKey).toEqual(["health", "ready"]);
    expect(options.staleTime).toBe(0);
    expect(options.retry).toBe(2);
    expect(options.refetchInterval).toBe(15_000);
    expect(options.refetchIntervalInBackground).toBe(false);
  });
});
