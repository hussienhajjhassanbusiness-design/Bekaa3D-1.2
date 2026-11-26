import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { notificationsApi } from "./notificationsApi";
import { useNotifications } from "./useNotifications";
import type { NotificationPageDTO, NotificationReadDTO } from "./notificationTypes";

// #ARCHITECTURE-NOTIFICATIONS-LIST-QUERY — mirrors useProducts.ts exactly:
// useInfiniteQuery matching the backend's {items, next_cursor} shape, no
// total/page-number/has_more guess. "Load more" appends a page.

function createWrapper() {
  const queryClient = new QueryClient();
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

function page(items: Partial<NotificationReadDTO>[], nextCursor: string | null): NotificationPageDTO {
  return { items: items as NotificationReadDTO[], next_cursor: nextCursor };
}

describe("useNotifications", () => {
  it("fetches the first page with no cursor", async () => {
    const listSpy = vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue(page([], null));
    const { result } = renderHook(() => useNotifications({}), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(listSpy).toHaveBeenCalledWith({ cursor: undefined });
  });

  it("derives hasNextPage from next_cursor !== null, never a guessed page count", async () => {
    vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue(page([{ id: "n1" }], "cursor-2"));
    const { result } = renderHook(() => useNotifications({}), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.hasNextPage).toBe(true);
  });

  it("hasNextPage is false when next_cursor is null", async () => {
    vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue(page([{ id: "n1" }], null));
    const { result } = renderHook(() => useNotifications({}), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.hasNextPage).toBe(false);
  });

  it("fetchNextPage requests the real next_cursor as the cursor param", async () => {
    const listSpy = vi
      .spyOn(notificationsApi, "listNotifications")
      .mockResolvedValueOnce(page([{ id: "n1" }], "cursor-2"))
      .mockResolvedValueOnce(page([{ id: "n2" }], null));
    const { result } = renderHook(() => useNotifications({}), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    await act(async () => {
      await result.current.fetchNextPage();
    });

    expect(listSpy).toHaveBeenLastCalledWith({ cursor: "cursor-2" });
  });

  it("passes the read filter through to every page request", async () => {
    const listSpy = vi.spyOn(notificationsApi, "listNotifications").mockResolvedValue(page([], null));
    const { result } = renderHook(() => useNotifications({ read: false }), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(listSpy).toHaveBeenCalledWith({ cursor: undefined, read: false });
  });
});
