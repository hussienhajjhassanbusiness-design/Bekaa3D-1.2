import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ManualConfirmDialog } from "./ManualConfirmDialog";

// FVS-028-IMPLEMENTATION-PLAN.md T04 — #SECURITY-MANUAL-PAYMENT-CONFIRMATION.
// Composes DialogShell directly, zero new focus-trap code. Manual
// confirmation must never be one casual click: Confirm stays disabled
// until both a non-empty reason AND the acknowledgment checkbox are
// satisfied, and the server-authoritative canManualConfirm/
// manualConfirmBlockedReason are never second-guessed locally.

const ACK_LABEL = "I have independently verified this payment.";

function renderDialog(overrides: Partial<Parameters<typeof ManualConfirmDialog>[0]> = {}) {
  const onClose = vi.fn();
  const onConfirm = vi.fn();
  render(
    <ManualConfirmDialog
      open={true}
      onClose={onClose}
      paymentId="pay-1"
      acknowledgmentLabel={ACK_LABEL}
      canManualConfirm={true}
      onConfirm={onConfirm}
      {...overrides}
    />
  );
  return { onClose, onConfirm };
}

describe("ManualConfirmDialog", () => {
  it("1. inherits DialogShell's real focus/dialog behavior (role=dialog, aria-modal) and closes on Escape", async () => {
    const { onClose } = renderDialog();
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");

    const user = userEvent.setup();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("2/4. disables Confirm with an empty reason", () => {
    renderDialog();
    expect(screen.getByRole("button", { name: /^confirm$/i })).toBeDisabled();
  });

  it("3/5. disables Confirm without the acknowledgment checkbox, even with a reason typed", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.type(screen.getByRole("textbox", { name: /reason/i }), "Verified with provider dashboard.");
    expect(screen.getByRole("button", { name: /^confirm$/i })).toBeDisabled();
  });

  it("disables Confirm with only acknowledgment checked and an empty reason", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(screen.getByRole("checkbox", { name: ACK_LABEL }));
    expect(screen.getByRole("button", { name: /^confirm$/i })).toBeDisabled();
  });

  it("6. enables Confirm once both reason and acknowledgment are satisfied", async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.type(screen.getByRole("textbox", { name: /reason/i }), "Verified with provider dashboard.");
    await user.click(screen.getByRole("checkbox", { name: ACK_LABEL }));
    expect(screen.getByRole("button", { name: /^confirm$/i })).toBeEnabled();
  });

  it("7. isConfirming disables Confirm regardless of reason/acknowledgment", async () => {
    const user = userEvent.setup();
    renderDialog({ isConfirming: true });
    await user.type(screen.getByRole("textbox", { name: /reason/i }), "Verified.");
    await user.click(screen.getByRole("checkbox", { name: ACK_LABEL }));
    expect(screen.getByRole("button", { name: /confirm/i })).toBeDisabled();
  });

  it("8. canManualConfirm: false disables Confirm regardless of reason/acknowledgment", async () => {
    const user = userEvent.setup();
    renderDialog({ canManualConfirm: false });
    await user.type(screen.getByRole("textbox", { name: /reason/i }), "Verified.");
    await user.click(screen.getByRole("checkbox", { name: ACK_LABEL }));
    expect(screen.getByRole("button", { name: /^confirm$/i })).toBeDisabled();
  });

  it("9. an already-paid-style manualConfirmBlockedReason renders visibly and still blocks Confirm", () => {
    renderDialog({ canManualConfirm: false, manualConfirmBlockedReason: "This payment has already been confirmed." });
    expect(screen.getByText("This payment has already been confirmed.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^confirm$/i })).toBeDisabled();
  });

  it("10. onConfirm receives the exact payment id and typed reason", async () => {
    const user = userEvent.setup();
    const { onConfirm } = renderDialog({ paymentId: "pay-42" });
    await user.type(screen.getByRole("textbox", { name: /reason/i }), "Verified with provider dashboard.");
    await user.click(screen.getByRole("checkbox", { name: ACK_LABEL }));
    await user.click(screen.getByRole("button", { name: /^confirm$/i }));

    expect(onConfirm).toHaveBeenCalledWith("pay-42", "Verified with provider dashboard.");
  });

  it("11. never makes a network/fetch call", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const user = userEvent.setup();
    renderDialog();
    await user.type(screen.getByRole("textbox", { name: /reason/i }), "Verified.");
    await user.click(screen.getByRole("checkbox", { name: ACK_LABEL }));
    await user.click(screen.getByRole("button", { name: /^confirm$/i }));
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("12. never persists the reason to localStorage or sessionStorage", async () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    const user = userEvent.setup();
    renderDialog();
    await user.type(screen.getByRole("textbox", { name: /reason/i }), "Verified.");
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  it("13. renders no raw provider payload anywhere — no such prop exists on this dialog's type", () => {
    renderDialog();
    expect(screen.queryByText(/webhook|signature|raw/i)).not.toBeInTheDocument();
  });

  it("14. Cancel calls onClose and never onConfirm", async () => {
    const user = userEvent.setup();
    const { onClose, onConfirm } = renderDialog();
    await user.type(screen.getByRole("textbox", { name: /reason/i }), "Verified.");
    await user.click(screen.getByRole("checkbox", { name: ACK_LABEL }));
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(onClose).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("renders a clear high-risk title explaining this bypasses normal verification", () => {
    renderDialog();
    expect(screen.getByText(/bypasses normal/i)).toBeInTheDocument();
  });
});
