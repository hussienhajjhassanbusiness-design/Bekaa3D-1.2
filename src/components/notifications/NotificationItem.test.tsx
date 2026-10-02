import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NotificationItem } from "./NotificationItem";
import { NOTIFICATION_RENDERERS } from "./notificationTypes";
import type { NotificationItemModel } from "./notificationTypes";

// FVS-008-IMPLEMENTATION-PLAN.md T02 — generic presentation only. No
// network calls, no TanStack Query ownership, no persistence. `type` is
// never assumed to have a special renderer — this slice ships zero
// concrete event types (NOTIFICATION_RENDERERS starts empty), so every
// notification in these tests exercises the SAME generic fallback path a
// real unknown future type would.

const UNREAD_NOTIFICATION: NotificationItemModel = {
  id: "n-1",
  type: "generic",
  title: "Welcome to Bekaa3D",
  body: "Thanks for joining — explore the shop to get started.",
  isRead: false,
};

const READ_NOTIFICATION: NotificationItemModel = { ...UNREAD_NOTIFICATION, id: "n-2", isRead: true };

describe("NotificationItem", () => {
  it("renders known generic data", () => {
    render(<NotificationItem notification={UNREAD_NOTIFICATION} onToggleRead={vi.fn()} />);
    expect(screen.getByText("Welcome to Bekaa3D")).toBeInTheDocument();
  });

  it("renders safely for a completely unrecognized type — the same generic path a real future type would hit", () => {
    const futureType: NotificationItemModel = { ...UNREAD_NOTIFICATION, type: "order-paid-v7-does-not-exist-yet" };
    render(<NotificationItem notification={futureType} onToggleRead={vi.fn()} />);
    expect(screen.getByText("Welcome to Bekaa3D")).toBeInTheDocument();
  });

  it("displays the exact title", () => {
    render(<NotificationItem notification={UNREAD_NOTIFICATION} onToggleRead={vi.fn()} />);
    expect(screen.getByText("Welcome to Bekaa3D")).toBeInTheDocument();
  });

  it("displays the exact body", () => {
    render(<NotificationItem notification={UNREAD_NOTIFICATION} onToggleRead={vi.fn()} />);
    expect(screen.getByText("Thanks for joining — explore the shop to get started.")).toBeInTheDocument();
  });

  it("never interprets title/body as HTML", () => {
    const withMarkup: NotificationItemModel = {
      ...UNREAD_NOTIFICATION,
      title: "<b>bold title</b>",
      body: "<img src=x onerror=alert(1)>",
    };
    render(<NotificationItem notification={withMarkup} onToggleRead={vi.fn()} />);

    expect(screen.getByText("<b>bold title</b>")).toBeInTheDocument();
    expect(document.querySelector("b")).toBeNull();
    expect(document.querySelector("img")).toBeNull();
  });

  it("conveys unread state with visible text, not only color", () => {
    render(<NotificationItem notification={UNREAD_NOTIFICATION} onToggleRead={vi.fn()} />);
    expect(screen.getByText(/unread/i)).toBeInTheDocument();
  });

  it("conveys read state with visible text", () => {
    render(<NotificationItem notification={READ_NOTIFICATION} onToggleRead={vi.fn()} />);
    expect(screen.getByText(/^read$/i)).toBeInTheDocument();
  });

  it("the action callback receives the exact id and the next read intent", async () => {
    const onToggleRead = vi.fn();
    const user = userEvent.setup();
    render(<NotificationItem notification={UNREAD_NOTIFICATION} onToggleRead={onToggleRead} />);

    await user.click(screen.getByRole("button", { name: /mark read/i }));

    expect(onToggleRead).toHaveBeenCalledWith("n-1", true);
  });

  it("the action callback for a read item requests marking it unread", async () => {
    const onToggleRead = vi.fn();
    const user = userEvent.setup();
    render(<NotificationItem notification={READ_NOTIFICATION} onToggleRead={onToggleRead} />);

    await user.click(screen.getByRole("button", { name: /mark unread/i }));

    expect(onToggleRead).toHaveBeenCalledWith("n-2", false);
  });

  it("disables the action control while isPending", () => {
    render(<NotificationItem notification={UNREAD_NOTIFICATION} onToggleRead={vi.fn()} isPending />);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<NotificationItem notification={UNREAD_NOTIFICATION} onToggleRead={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<NotificationItem notification={UNREAD_NOTIFICATION} onToggleRead={vi.fn()} />);
    expect(spy).not.toHaveBeenCalled();
  });

  it("ships with zero concrete event-type renderers", () => {
    expect(Object.keys(NOTIFICATION_RENDERERS)).toHaveLength(0);
  });
});
