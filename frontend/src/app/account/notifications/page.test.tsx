import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AccountNotificationsPage from "./page";
import { useNotifications } from "@/lib/notifications/useNotifications";
import { useSetNotificationRead } from "@/lib/notifications/useSetNotificationRead";

// Phase 2 auth/account batch (FVS-008) — mocks the owning hooks (not
// apiClient/fetch), matching the page-test precedent elsewhere. The
// hooks' own transport wiring is proven separately.

vi.mock("@/lib/notifications/useNotifications", () => ({ useNotifications: vi.fn() }));
vi.mock("@/lib/notifications/useSetNotificationRead", () => ({ useSetNotificationRead: vi.fn() }));

const mockedUseNotifications = vi.mocked(useNotifications);
const mockedUseSetNotificationRead = vi.mocked(useSetNotificationRead);

function queryResult(overrides: Record<string, unknown> = {}) {
  return {
    data: { pages: [{ items: [], next_cursor: null }], pageParams: [undefined] },
    isLoading: false,
    isError: false,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    refetch: vi.fn(),
    ...overrides,
  };
}

function notificationDto(overrides: Record<string, unknown> = {}) {
  return { id: "n1", type: "account", payload: {}, read: false, created_at: "2026-01-01T00:00:00Z", ...overrides };
}

beforeEach(() => {
  mockedUseNotifications.mockReset();
  mockedUseSetNotificationRead.mockReset();
  mockedUseSetNotificationRead.mockReturnValue({ mutateAsync: vi.fn() } as never);
});

describe("AccountNotificationsPage (/account/notifications)", () => {
  it("renders a loading state while the first page is loading", () => {
    mockedUseNotifications.mockReturnValue(queryResult({ data: undefined, isLoading: true }) as never);
    render(<AccountNotificationsPage />);

    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders an empty state when there are no notifications", async () => {
    mockedUseNotifications.mockReturnValue(queryResult() as never);
    render(<AccountNotificationsPage />);

    expect(await screen.findByText(/no notifications/i)).toBeInTheDocument();
  });

  it("renders an error state with a retry action on failure", async () => {
    const refetch = vi.fn();
    mockedUseNotifications.mockReturnValue(queryResult({ data: undefined, isError: true, refetch }) as never);
    render(<AccountNotificationsPage />);

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /retry/i }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("renders a populated list, deriving title/body safely via the adapter (never crashing on an unknown event)", async () => {
    mockedUseNotifications.mockReturnValue(
      queryResult({
        data: {
          pages: [{ items: [notificationDto({ payload: { event: "some_unregistered_future_event" } })], next_cursor: null }],
          pageParams: [undefined],
        },
      }) as never
    );
    render(<AccountNotificationsPage />);

    expect(await screen.findByText(/account update: some_unregistered_future_event/i)).toBeInTheDocument();
    expect(screen.getByText(/unread/i)).toBeInTheDocument();
  });

  it("shows a Load more control when hasNextPage is true, and calls fetchNextPage on click", async () => {
    const fetchNextPage = vi.fn();
    mockedUseNotifications.mockReturnValue(
      queryResult({
        data: { pages: [{ items: [notificationDto()], next_cursor: "c2" }], pageParams: [undefined] },
        hasNextPage: true,
        fetchNextPage,
      }) as never
    );
    render(<AccountNotificationsPage />);

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /load more/i }));
    expect(fetchNextPage).toHaveBeenCalledTimes(1);
  });

  it("marking a notification read calls the mutation with { id, read: true }", async () => {
    const mutateAsync = vi.fn().mockResolvedValue(undefined);
    mockedUseSetNotificationRead.mockReturnValue({ mutateAsync } as never);
    mockedUseNotifications.mockReturnValue(
      queryResult({ data: { pages: [{ items: [notificationDto({ read: false })], next_cursor: null }], pageParams: [undefined] } }) as never
    );
    render(<AccountNotificationsPage />);

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /mark read/i }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ id: "n1", read: true }));
  });

  it("shows a friendly message (not the raw backend code) when marking read fails with CSRF_INVALID", async () => {
    const mutateAsync = vi.fn().mockRejectedValue({ kind: "http", status: 403, code: "CSRF_INVALID", message: "x", raw: {} });
    mockedUseSetNotificationRead.mockReturnValue({ mutateAsync } as never);
    mockedUseNotifications.mockReturnValue(
      queryResult({ data: { pages: [{ items: [notificationDto({ read: false })], next_cursor: null }], pageParams: [undefined] } }) as never
    );
    render(<AccountNotificationsPage />);

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /mark read/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).not.toHaveTextContent("CSRF_INVALID");
  });
});
