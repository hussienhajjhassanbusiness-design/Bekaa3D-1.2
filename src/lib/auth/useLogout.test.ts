import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { useLogout } from "./useLogout";
import { AUTH_SESSION_QUERY_KEY } from "./authSession";
import * as crossTabSignalModule from "./crossTabSignal";
import * as authenticatedRequestModule from "./authenticatedRequest";

// FVS-003-IMPLEMENTATION-PLAN.md §9/Part E (confirmed BATCH 3B) —
// local-first logout: local auth state is cleared synchronously before any
// network response, broadcast cross-tab, then the server call is
// attempted. 204 and 401 AUTH_REQUIRED both count as confirmed server
// success; everything else gets exactly one bounded background retry
// (never forever, never authenticatedRequest). mutateAsync always
// resolves — the user's own logout action is never a failed action,
// since the frontend is already locally logged out regardless of the
// server outcome.

function createWrapper() {
  const queryClient = new QueryClient();
  queryClient.setQueryData(AUTH_SESSION_QUERY_KEY, {
    id: "u-1",
    email: "ada@example.com",
    role: "customer",
    emailVerified: true,
    emailVerifiedAt: null,
    createdAt: "2026-01-01T00:00:00Z",
  });
  return { queryClient, Wrapper: ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children) };
}

function httpError(status: number, code?: string): ApiError {
  return { kind: "http", status, code, message: "x", raw: undefined };
}
function networkError(): ApiError {
  return { kind: "network", message: "x", raw: undefined };
}
function csrfError(): ApiError {
  return { kind: "csrf", message: "x", raw: undefined };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("useLogout", () => {
  it("calls the exact path, no body, csrf:true, directly via apiClient (never authenticatedRequest)", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue(undefined);
    const authenticatedRequestSpy = vi.spyOn(authenticatedRequestModule, "authenticatedRequest");
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync();
    });

    expect(postSpy).toHaveBeenCalledTimes(1);
    const [path, body, options] = postSpy.mock.calls[0] as [string, unknown, Record<string, unknown> | undefined];
    expect(path).toBe("/api/v1/auth/logout");
    expect(body).toBeUndefined();
    expect(options?.csrf).toBe(true);
    expect(authenticatedRequestSpy).not.toHaveBeenCalled();
  });

  it("retry: false is configured at the mutation layer — never auto-retried by TanStack, even past its backoff window", async () => {
    vi.useFakeTimers();
    vi.spyOn(apiClient, "post").mockResolvedValue(undefined);
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    // Exactly the initial call — no TanStack-level retry of a rejected
    // mutationFn (this mutationFn never rejects at all, by design).
    expect(apiClient.post).toHaveBeenCalledTimes(1);
  });

  it("clears the local auth session to anonymous synchronously, before the network call resolves", async () => {
    let resolvePost!: () => void;
    vi.spyOn(apiClient, "post").mockReturnValue(
      new Promise((resolve) => {
        resolvePost = () => resolve(undefined);
      })
    );
    const { Wrapper, queryClient } = createWrapper();
    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });

    let pending!: Promise<unknown>;
    act(() => {
      pending = result.current.mutateAsync();
    });

    // mutateAsync() returns before mutationFn's own synchronous prefix is
    // guaranteed to have run (TanStack defers it by a microtask) — poll for
    // the condition rather than asserting immediately after the sync call.
    await waitFor(() => expect(queryClient.getQueryData(AUTH_SESSION_QUERY_KEY)).toBeNull());

    await act(async () => {
      resolvePost();
      await pending;
    });
  });

  it("broadcasts exactly one 'logout' cross-tab signal, regardless of the eventual server outcome", async () => {
    const announceSpy = vi.fn();
    vi.spyOn(crossTabSignalModule, "createCrossTabSignal").mockReturnValue({
      announce: announceSpy,
      subscribe: vi.fn(() => () => {}),
      close: vi.fn(),
    });
    vi.spyOn(apiClient, "post").mockRejectedValue(networkError());
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync();
    });

    expect(announceSpy).toHaveBeenCalledTimes(1);
    expect(announceSpy).toHaveBeenCalledWith("logout");
  });

  it("a 204 (resolved post) is treated as confirmed server success — mutateAsync resolves serverConfirmed:true, no retry needed", async () => {
    vi.useFakeTimers();
    vi.spyOn(apiClient, "post").mockResolvedValue(undefined);
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });

    const outcome = await act(async () => result.current.mutateAsync());
    expect(outcome).toEqual({ serverConfirmed: true });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(apiClient.post).toHaveBeenCalledTimes(1);
  });

  it("a 401 AUTH_REQUIRED failure is treated as confirmed server success — no retry scheduled", async () => {
    vi.useFakeTimers();
    vi.spyOn(apiClient, "post").mockRejectedValue(httpError(401, "AUTH_REQUIRED"));
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });

    const outcome = await act(async () => result.current.mutateAsync());
    expect(outcome).toEqual({ serverConfirmed: true });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(apiClient.post).toHaveBeenCalledTimes(1);
  });

  it("a 403 CSRF_INVALID failure is NOT treated as server success, but mutateAsync still resolves (never rejects) — the user stays locally logged out", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(httpError(403, "CSRF_INVALID"));
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });

    const outcome = await act(async () => result.current.mutateAsync());
    expect(outcome).toEqual({ serverConfirmed: false });
  });

  it("a network failure is NOT treated as server success, but still resolves without throwing", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(networkError());
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });

    await expect(act(async () => result.current.mutateAsync())).resolves.toEqual({ serverConfirmed: false });
  });

  it("schedules exactly one bounded background retry after a non-success outcome", async () => {
    vi.useFakeTimers();
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(networkError());
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync();
    });
    expect(postSpy).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(postSpy).toHaveBeenCalledTimes(2);
  });

  it("never retries more than once, even if the background retry also fails and timers advance repeatedly", async () => {
    vi.useFakeTimers();
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(networkError());
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300_000);
    });

    expect(postSpy).toHaveBeenCalledTimes(2);
  });

  it("the background retry also sends csrf:true", async () => {
    vi.useFakeTimers();
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(networkError());
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    const secondCallOptions = postSpy.mock.calls[1]?.[2] as Record<string, unknown> | undefined;
    expect(secondCallOptions?.csrf).toBe(true);
  });

  it("a missing CSRF token (local 'csrf' ApiError) on the initial attempt is treated as a failure, triggers the bounded retry, and never throws out of mutateAsync", async () => {
    vi.useFakeTimers();
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(csrfError());
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });

    const outcome = await act(async () => result.current.mutateAsync());
    expect(outcome).toEqual({ serverConfirmed: false });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(postSpy).toHaveBeenCalledTimes(2);
  });

  it("if the scheduled retry itself fails, nothing throws and no further retry is scheduled", async () => {
    vi.useFakeTimers();
    const postSpy = vi.spyOn(apiClient, "post").mockRejectedValue(networkError());
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(postSpy).toHaveBeenCalledTimes(2);
  });

  it("mutateAsync always resolves, never rejects, regardless of the backend outcome", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(httpError(500, "SERVER_ERROR"));
    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });

    await expect(act(async () => result.current.mutateAsync())).resolves.toEqual({ serverConfirmed: false });
  });
});

describe("useLogout: user-scoped cache (Phase 5A defect 7)", () => {
  it("drops cached admin and notification data synchronously, but keeps public catalogue data", async () => {
    let resolvePost!: () => void;
    vi.spyOn(apiClient, "post").mockReturnValue(new Promise((resolve) => (resolvePost = () => resolve(undefined))));
    const { queryClient, Wrapper } = createWrapper();
    queryClient.setQueryData(["admin", "customers", "list", {}], { items: [{ email: "someone@example.com" }] });
    queryClient.setQueryData(["admin", "products", "detail", "p-1"], { id: "p-1" });
    queryClient.setQueryData(["notifications", "list", {}], { items: [{ id: "n-1" }] });
    queryClient.setQueryData(["products", "list", {}], { items: [] });
    queryClient.setQueryData(["publicSettings", "current"], { accepting_orders: true });
    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });

    act(() => {
      void result.current.mutateAsync();
    });

    await waitFor(() => expect(queryClient.getQueryData(AUTH_SESSION_QUERY_KEY)).toBeNull());
    expect(queryClient.getQueryCache().findAll({ queryKey: ["admin"] })).toHaveLength(0);
    expect(queryClient.getQueryCache().findAll({ queryKey: ["notifications"] })).toHaveLength(0);
    expect(queryClient.getQueryData(["products", "list", {}])).toEqual({ items: [] });
    expect(queryClient.getQueryData(["publicSettings", "current"])).toEqual({ accepting_orders: true });

    await act(async () => {
      resolvePost();
    });
  });
});
