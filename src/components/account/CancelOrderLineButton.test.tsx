import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CancelOrderLineButton } from "./CancelOrderLineButton";
import type { OrderActionAffordance } from "@/lib/orders/orderActionModel";

// FVS-031-IMPLEMENTATION-PLAN.md T02/T03 — composes the shared
// OrderActionButtons primitive with a single caller-supplied action,
// the same architecture FVS-030 established
// (#SECURITY-SERVER-CANCELLATION-AUTHORITY). The errorMessage prop
// (mirroring InternalNoteEditor/ManualConfirmDialog's established
// pattern) is the race-lost/generic-failure feedback seam — no
// separate taxonomy component.

const ACTION: OrderActionAffordance = { id: "customer-cancel", label: "Cancel this item", requiresConfirmation: true };

describe("CancelOrderLineButton", () => {
  it("renders the cancel button when a legal action is supplied", () => {
    render(<CancelOrderLineButton action={ACTION} onCancel={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Cancel this item" })).toBeInTheDocument();
  });

  it("renders nothing when no legal action is supplied — never a permanently disabled button", () => {
    render(<CancelOrderLineButton action={null} onCancel={vi.fn()} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("requires confirmation before calling onCancel, reusing the shared ConfirmDialog", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(<CancelOrderLineButton action={ACTION} onCancel={onCancel} />);

    await user.click(screen.getByRole("button", { name: "Cancel this item" }));
    expect(onCancel).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onCancel).toHaveBeenCalledWith("customer-cancel");
  });

  it("an action not requiring confirmation fires onCancel immediately", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(
      <CancelOrderLineButton
        action={{ id: "customer-cancel", label: "Cancel this item", requiresConfirmation: false }}
        onCancel={onCancel}
      />
    );

    await user.click(screen.getByRole("button", { name: "Cancel this item" }));
    expect(onCancel).toHaveBeenCalledWith("customer-cancel");
  });

  it("disables the button while pendingActionId matches the action", () => {
    render(<CancelOrderLineButton action={ACTION} pendingActionId="customer-cancel" onCancel={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Cancel this item" })).toBeDisabled();
  });

  it("renders the caller-supplied errorMessage verbatim — no raw backend text, no invented copy", () => {
    render(
      <CancelOrderLineButton
        action={ACTION}
        errorMessage="This item can no longer be cancelled because fulfillment has progressed."
        onCancel={vi.fn()}
      />
    );
    expect(
      screen.getByText("This item can no longer be cancelled because fulfillment has progressed.")
    ).toBeInTheDocument();
  });

  it("renders no error text when errorMessage is absent", () => {
    render(<CancelOrderLineButton action={ACTION} onCancel={vi.fn()} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("never retries automatically and never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<CancelOrderLineButton action={ACTION} onCancel={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
