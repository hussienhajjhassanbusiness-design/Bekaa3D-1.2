import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfirmDialog } from "./ConfirmDialog";

// FVS-007-IMPLEMENTATION-PLAN.md T04 — generic, reusable confirmation
// modal. No existing dialog infrastructure was found anywhere in this
// repository to reuse (searched first, per the task's own instruction).
// Carries NO setting/business-domain knowledge of any kind — props are
// deliberately generic (title/description strings only).
//
// Native <dialog>.showModal()/.close() is not implemented by this
// project's jsdom version (confirmed empirically — showModal throws
// "not a function"), which would make this component untestable at the
// unit level despite working in a real browser. Built instead as a
// manually-managed accessible dialog (role="dialog", aria-modal, a
// simple Tab focus trap, Escape handling) — the same pattern most
// non-native dialog libraries implement internally, and fully testable
// here.

function renderDialog(overrides: Partial<Parameters<typeof ConfirmDialog>[0]> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <ConfirmDialog
      open={true}
      title="Turn off accepting orders?"
      description="Customers will be unable to place new orders until this is turned back on."
      onConfirm={onConfirm}
      onCancel={onCancel}
      {...overrides}
    />
  );
  return { onConfirm, onCancel };
}

describe("ConfirmDialog", () => {
  it("is absent from the DOM when closed", () => {
    render(<ConfirmDialog open={false} title="t" description="d" onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("is visible when open", () => {
    renderDialog();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("associates the title via aria-labelledby", () => {
    renderDialog();
    const dialog = screen.getByRole("dialog");
    const labelledBy = dialog.getAttribute("aria-labelledby");
    expect(labelledBy).toBeTruthy();
    expect(document.getElementById(labelledBy!)).toHaveTextContent("Turn off accepting orders?");
  });

  it("associates the description via aria-describedby", () => {
    renderDialog();
    const dialog = screen.getByRole("dialog");
    const describedBy = dialog.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy!)).toHaveTextContent(/unable to place new orders/i);
  });

  it("calls onCancel when Cancel is clicked", async () => {
    const user = userEvent.setup();
    const { onCancel } = renderDialog();

    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("calls onConfirm when Confirm is clicked", async () => {
    const user = userEvent.setup();
    const { onConfirm } = renderDialog();

    await user.click(screen.getByRole("button", { name: /confirm/i }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("disables Confirm (and Cancel) while isConfirming is true", () => {
    renderDialog({ isConfirming: true });
    expect(screen.getByRole("button", { name: /confirm/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeDisabled();
  });

  it("Escape calls onCancel when not confirming", async () => {
    const user = userEvent.setup();
    const { onCancel } = renderDialog();

    await user.keyboard("{Escape}");

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("Escape does nothing while isConfirming is true — closing mid-confirm is not safe", async () => {
    const user = userEvent.setup();
    const { onCancel } = renderDialog({ isConfirming: true });

    await user.keyboard("{Escape}");

    expect(onCancel).not.toHaveBeenCalled();
  });

  it("keeps keyboard focus trapped within the dialog (Tab from the last control wraps to the first)", async () => {
    const user = userEvent.setup();
    renderDialog();

    const cancelButton = screen.getByRole("button", { name: /cancel/i });
    const confirmButton = screen.getByRole("button", { name: /confirm/i });

    confirmButton.focus();
    expect(confirmButton).toHaveFocus();
    await user.tab();

    expect(cancelButton).toHaveFocus();
  });

  it("carries no setting/business-key knowledge — only renders exactly the generic title/description strings it was given", () => {
    renderDialog({ title: "Generic title", description: "Generic description" });

    expect(screen.getByText("Generic title")).toBeInTheDocument();
    expect(screen.getByText("Generic description")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/accepting-orders|offer-floor|whatsapp/i);
  });
});
