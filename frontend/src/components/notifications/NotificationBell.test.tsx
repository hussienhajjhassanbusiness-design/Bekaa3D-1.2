import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NotificationBell } from "./NotificationBell";

// FVS-008-IMPLEMENTATION-PLAN.md T04 — pure presentation, standalone (not
// yet mounted into Header — see the plan's own scope note). No data
// fetch, no polling, no mutation. Tests cover accessibility and
// responsive structural semantics only, never a fake API/unread-count-
// fetching behavior.

describe("NotificationBell", () => {
  it("has the exact accessible label format for a nonzero unread count", () => {
    render(
      <NotificationBell unreadCount={3} open={false} onOpenChange={vi.fn()}>
        content
      </NotificationBell>
    );
    expect(screen.getByRole("button", { name: "Notifications, 3 unread" })).toBeInTheDocument();
  });

  it("uses the same format for zero unread, never a silent reinterpretation", () => {
    render(
      <NotificationBell unreadCount={0} open={false} onOpenChange={vi.fn()}>
        content
      </NotificationBell>
    );
    expect(screen.getByRole("button", { name: "Notifications, 0 unread" })).toBeInTheDocument();
  });

  it("does not render the panel when closed", () => {
    render(
      <NotificationBell unreadCount={1} open={false} onOpenChange={vi.fn()}>
        <div data-testid="panel-content">content</div>
      </NotificationBell>
    );
    expect(screen.queryByTestId("panel-content")).not.toBeInTheDocument();
  });

  it("renders the panel with its content when open", () => {
    render(
      <NotificationBell unreadCount={1} open={true} onOpenChange={vi.fn()}>
        <div data-testid="panel-content">content</div>
      </NotificationBell>
    );
    expect(screen.getByTestId("panel-content")).toBeInTheDocument();
  });

  it("clicking the bell requests the opposite open state", async () => {
    const onOpenChange = vi.fn();
    const user = userEvent.setup();
    render(
      <NotificationBell unreadCount={1} open={false} onOpenChange={onOpenChange}>
        content
      </NotificationBell>
    );

    await user.click(screen.getByRole("button", { name: /notifications/i }));

    expect(onOpenChange).toHaveBeenCalledWith(true);
  });

  it("Escape requests closing while open", async () => {
    const onOpenChange = vi.fn();
    const user = userEvent.setup();
    render(
      <NotificationBell unreadCount={1} open={true} onOpenChange={onOpenChange}>
        <button type="button">inside</button>
      </NotificationBell>
    );

    await user.keyboard("{Escape}");

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("does not react to Escape while closed", async () => {
    const onOpenChange = vi.fn();
    const user = userEvent.setup();
    render(
      <NotificationBell unreadCount={1} open={false} onOpenChange={onOpenChange}>
        content
      </NotificationBell>
    );

    await user.keyboard("{Escape}");

    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it("traps Tab focus within the open panel", async () => {
    const user = userEvent.setup();
    render(
      <NotificationBell unreadCount={1} open={true} onOpenChange={vi.fn()}>
        <button type="button">only-focusable</button>
      </NotificationBell>
    );

    const onlyButton = screen.getByRole("button", { name: "only-focusable" });
    onlyButton.focus();
    expect(onlyButton).toHaveFocus();

    await user.tab();

    expect(onlyButton).toHaveFocus();
  });

  it("clicking outside the open panel requests closing", async () => {
    const onOpenChange = vi.fn();
    const user = userEvent.setup();
    render(
      <div>
        <NotificationBell unreadCount={1} open={true} onOpenChange={onOpenChange}>
          <div data-testid="panel-content">content</div>
        </NotificationBell>
        <div data-testid="outside">outside</div>
      </div>
    );

    await user.click(screen.getByTestId("outside"));

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("clicking inside the open panel does not request closing", async () => {
    const onOpenChange = vi.fn();
    const user = userEvent.setup();
    render(
      <NotificationBell unreadCount={1} open={true} onOpenChange={onOpenChange}>
        <div data-testid="panel-content">content</div>
      </NotificationBell>
    );

    await user.click(screen.getByTestId("panel-content"));

    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it("carries responsive structural classes for a full-screen mobile sheet and an anchored desktop dropdown", () => {
    render(
      <NotificationBell unreadCount={1} open={true} onOpenChange={vi.fn()}>
        content
      </NotificationBell>
    );
    const panel = screen.getByRole("dialog");
    expect(panel.className).toMatch(/fixed inset-0/);
    expect(panel.className).toMatch(/tablet:absolute/);
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(
      <NotificationBell unreadCount={1} open={true} onOpenChange={vi.fn()}>
        content
      </NotificationBell>
    );
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(
      <NotificationBell unreadCount={1} open={true} onOpenChange={vi.fn()}>
        content
      </NotificationBell>
    );
    expect(spy).not.toHaveBeenCalled();
  });
});
