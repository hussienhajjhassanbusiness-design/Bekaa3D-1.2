import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { notificationsApi } from "./notificationsApi";
import { notificationsKeys } from "./notificationsApi";
import { useSetNotificationRead } from "./useSetNotificationRead";

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useSetNotificationRead", () => {
  it("calls notificationsApi.setNotificationRead with the given id and read value", async () => {
    const setSpy = vi
      .spyOn(notificationsApi, "setNotificationRead")
      .mockResolvedValue({ id: "n1", type: "account", payload: {}, read: true, created_at: "2026-01-01T00:00:00Z" });
    const queryClient = new QueryClient();
    const { result } = renderHook(() => useSetNotificationRead(), { wrapper: createWrapper(queryClient) });

    await act(async () => {
      await result.current.mutateAsync({ id: "n1", read: true });
    });

    expect(setSpy).toHaveBeenCalledWith("n1", true);
  });

  it("invalidates the notifications list query on success, so the list reflects the new read state", async () => {
    vi.spyOn(notificationsApi, "setNotificationRead").mockResolvedValue({
      id: "n1",
      type: "account",
      payload: {},
      read: true,
      created_at: "2026-01-01T00:00:00Z",
    });
    const queryClient = new QueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useSetNotificationRead(), { wrapper: createWrapper(queryClient) });

    await act(async () => {
      await result.current.mutateAsync({ id: "n1", read: true });
    });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: notificationsKeys.root });
  });

  it("surfaces a rejection unchanged on failure", async () => {
    const error = { kind: "http" as const, status: 403, code: "CSRF_INVALID", message: "x", raw: {} };
    vi.spyOn(notificationsApi, "setNotificationRead").mockRejectedValue(error);
    const queryClient = new QueryClient();
    const { result } = renderHook(() => useSetNotificationRead(), { wrapper: createWrapper(queryClient) });

    await act(async () => {
      await expect(result.current.mutateAsync({ id: "n1", read: true })).rejects.toMatchObject({
        status: 403,
        code: "CSRF_INVALID",
      });
    });
  });
});
