import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MessageDetail } from "./MessageDetail";
import type { MessageDetailModel } from "./MessageDetail";

// FVS-017-IMPLEMENTATION-PLAN.md T03 — only name/email/message/status
// are rendered (VS-015-confirmed fields) — no IP/user-agent/captcha-
// score/internal-notes/database-metadata/moderation-flags
// (#SECURITY-CONTACT-PII). Only the single legal next action renders —
// no status dropdown, no free-text, no arbitrary transition selector.

function makeMessage(overrides: Partial<MessageDetailModel> = {}): MessageDetailModel {
  return { name: "Ada Lovelace", email: "ada@example.com", message: "Interested in a custom stand.", status: "new", ...overrides };
}

describe("MessageDetail", () => {
  it("renders the name", () => {
    render(<MessageDetail message={makeMessage()} onTransition={vi.fn()} />);
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
  });

  it("renders the email as a mailto link", () => {
    render(<MessageDetail message={makeMessage()} onTransition={vi.fn()} />);
    expect(screen.getByRole("link", { name: "ada@example.com" })).toHaveAttribute("href", "mailto:ada@example.com");
  });

  it("renders the message text", () => {
    render(<MessageDetail message={makeMessage()} onTransition={vi.fn()} />);
    expect(screen.getByText("Interested in a custom stand.")).toBeInTheDocument();
  });

  it("preserves multiline message content without HTML interpretation", () => {
    render(<MessageDetail message={makeMessage({ message: "Line one\nLine two" })} onTransition={vi.fn()} />);
    const node = screen.getByText((text) => text.includes("Line one") && text.includes("Line two"));
    expect(node).toHaveStyle({ whiteSpace: "pre-wrap" });
  });

  it("renders an HTML-like message literally, never interpreted", () => {
    render(<MessageDetail message={makeMessage({ message: "<b>bold</b>" })} onTransition={vi.fn()} />);
    expect(screen.getByText("<b>bold</b>")).toBeInTheDocument();
    expect(document.querySelector("b")).toBeNull();
  });

  it("renders the current status as text via StatusBadge", () => {
    render(<MessageDetail message={makeMessage({ status: "replied" })} onTransition={vi.fn()} />);
    expect(screen.getByText("Replied")).toBeInTheDocument();
  });

  it("renders only the single legal next action for a new message", () => {
    render(<MessageDetail message={makeMessage({ status: "new" })} onTransition={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Mark read" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark replied" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Archive" })).not.toBeInTheDocument();
  });

  it("renders only the single legal next action for a read message", () => {
    render(<MessageDetail message={makeMessage({ status: "read" })} onTransition={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Mark replied" })).toBeInTheDocument();
  });

  it("renders no action for an archived message", () => {
    render(<MessageDetail message={makeMessage({ status: "archived" })} onTransition={vi.fn()} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("calls onTransition with the exact next status when the action is activated", async () => {
    const onTransition = vi.fn();
    const user = userEvent.setup();
    render(<MessageDetail message={makeMessage({ status: "new" })} onTransition={onTransition} />);

    await user.click(screen.getByRole("button", { name: "Mark read" }));

    expect(onTransition).toHaveBeenCalledWith("read");
  });

  it("disables the action while isPending", () => {
    render(<MessageDetail message={makeMessage({ status: "new" })} onTransition={vi.fn()} isPending />);
    expect(screen.getByRole("button", { name: "Mark read" })).toBeDisabled();
  });

  it("shows a safe, caller-supplied error message", () => {
    render(<MessageDetail message={makeMessage()} onTransition={vi.fn()} error="Could not update this message." />);
    expect(screen.getByText("Could not update this message.")).toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<MessageDetail message={makeMessage()} onTransition={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<MessageDetail message={makeMessage()} onTransition={vi.fn()} />);
    expect(spy).not.toHaveBeenCalled();
  });
});
