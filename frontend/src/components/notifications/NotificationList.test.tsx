import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NotificationList } from "./NotificationList";
import type { NotificationItemModel } from "./notificationTypes";

// FVS-008-IMPLEMENTATION-PLAN.md T03 — presentational list states only.
// Never parses a backend error (errorMessage is already a safe, external
// string); pagination is fully generic (canLoadMore/isLoadingMore/
// onLoadMore) — no page/cursor field assumed anywhere here.

const ITEMS: NotificationItemModel[] = [
  { id: "n-1", type: "generic", title: "First", body: "First body", isRead: false },
  { id: "n-2", type: "generic", title: "Second", body: "Second body", isRead: true },
];

describe("NotificationList", () => {
  it("shows a loading state", () => {
    render(<NotificationList notifications={[]} isLoading onToggleRead={vi.fn()} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows a safe error message", () => {
    render(
      <NotificationList
        notifications={[]}
        isError
        errorMessage="We couldn't load your notifications. Please try again."
        onToggleRead={vi.fn()}
      />
    );
    expect(screen.getByRole("alert")).toHaveTextContent("We couldn't load your notifications. Please try again.");
  });

  it("retry calls the provided callback", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<NotificationList notifications={[]} isError errorMessage="Failed." onRetry={onRetry} onToggleRead={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /retry/i }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows a safe empty-inbox message when there are no notifications", () => {
    render(<NotificationList notifications={[]} onToggleRead={vi.fn()} />);
    expect(screen.getByText(/no notifications/i)).toBeInTheDocument();
  });

  it("renders a real semantic list when populated", () => {
    render(<NotificationList notifications={ITEMS} onToggleRead={vi.fn()} />);
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("renders multiple items correctly", () => {
    render(<NotificationList notifications={ITEMS} onToggleRead={vi.fn()} />);
    expect(screen.getByText("First")).toBeInTheDocument();
    expect(screen.getByText("Second")).toBeInTheDocument();
  });

  it("shows a Load more control when canLoadMore is true", () => {
    render(<NotificationList notifications={ITEMS} canLoadMore onLoadMore={vi.fn()} onToggleRead={vi.fn()} />);
    expect(screen.getByRole("button", { name: /load more/i })).toBeInTheDocument();
  });

  it("omits the Load more control when exhausted", () => {
    render(<NotificationList notifications={ITEMS} canLoadMore={false} onToggleRead={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument();
  });

  it("disables Load more while isLoadingMore", () => {
    render(
      <NotificationList notifications={ITEMS} canLoadMore isLoadingMore onLoadMore={vi.fn()} onToggleRead={vi.fn()} />
    );
    expect(screen.getByRole("button", { name: /load more/i })).toBeDisabled();
  });

  it("forwards the toggle-read action from a child item unchanged", async () => {
    const onToggleRead = vi.fn();
    const user = userEvent.setup();
    render(<NotificationList notifications={ITEMS} onToggleRead={onToggleRead} />);

    const [firstActionButton] = screen.getAllByRole("button", { name: /mark (read|unread)/i });
    await user.click(firstActionButton!);

    expect(onToggleRead).toHaveBeenCalledWith("n-1", true);
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<NotificationList notifications={ITEMS} onToggleRead={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<NotificationList notifications={ITEMS} onToggleRead={vi.fn()} />);
    expect(spy).not.toHaveBeenCalled();
  });
});
