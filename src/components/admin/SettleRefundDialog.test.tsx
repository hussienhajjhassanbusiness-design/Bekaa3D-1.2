import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SettleRefundDialog } from "./SettleRefundDialog";

// FVS-032-IMPLEMENTATION-PLAN.md T07 — mirrors ManualConfirmDialog's
// (FVS-028) DialogShell + explicit-acknowledgment pattern exactly (no
// reason field — VS-026 does not mention one for settlement).
// canSettle/blockedReason are server-authoritative — this dialog
// never second-guesses them locally
// (#SECURITY-SERVER-REFUND-BALANCE-AUTHORITY). No optimistic
// "settled" UI anywhere — onConfirm is the only thing this dialog
// does; the caller's refetch decides what renders next.

describe("SettleRefundDialog", () => {
  it("renders the refund identity, amount, and settlement method", () => {
    render(
      <SettleRefundDialog
        open
        refundId="refund-1"
        amountCents={2000}
        currency="USD"
        settlementMethodLabel="Manual"
        acknowledgmentLabel="I confirm this refund has been paid out."
        canSettle
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />
    );
    expect(screen.getByText(/refund-1/)).toBeInTheDocument();
    expect(screen.getByText("$20.00")).toBeInTheDocument();
    expect(screen.getByText("Manual")).toBeInTheDocument();
  });

  it("Confirm stays disabled until the acknowledgment checkbox is checked", async () => {
    const user = userEvent.setup();
    render(
      <SettleRefundDialog
        open
        refundId="refund-1"
        amountCents={2000}
        currency="USD"
        settlementMethodLabel="Manual"
        acknowledgmentLabel="I confirm this refund has been paid out."
        canSettle
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: "Confirm" })).toBeEnabled();
  });

  it("confirming calls onConfirm with the refundId", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <SettleRefundDialog
        open
        refundId="refund-9"
        amountCents={2000}
        currency="USD"
        settlementMethodLabel="Manual"
        acknowledgmentLabel="I confirm this refund has been paid out."
        canSettle
        onClose={vi.fn()}
        onConfirm={onConfirm}
      />
    );

    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(onConfirm).toHaveBeenCalledWith("refund-9");
  });

  it("Confirm stays disabled when canSettle is false, even after acknowledging — server-authoritative", async () => {
    const user = userEvent.setup();
    render(
      <SettleRefundDialog
        open
        refundId="refund-1"
        amountCents={2000}
        currency="USD"
        settlementMethodLabel="Manual"
        acknowledgmentLabel="I confirm this refund has been paid out."
        canSettle={false}
        blockedReason="This refund was already settled."
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />
    );

    await user.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
    expect(screen.getByText("This refund was already settled.")).toBeInTheDocument();
  });

  it("disables Confirm and Cancel while isSettling is true", async () => {
    const user = userEvent.setup();
    render(
      <SettleRefundDialog
        open
        refundId="refund-1"
        amountCents={2000}
        currency="USD"
        settlementMethodLabel="Manual"
        acknowledgmentLabel="I confirm this refund has been paid out."
        canSettle
        isSettling
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />
    );

    await user.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  });

  it("does not render when open is false", () => {
    render(
      <SettleRefundDialog
        open={false}
        refundId="refund-1"
        amountCents={2000}
        currency="USD"
        settlementMethodLabel="Manual"
        acknowledgmentLabel="I confirm this refund has been paid out."
        canSettle
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(
      <SettleRefundDialog
        open
        refundId="refund-1"
        amountCents={2000}
        currency="USD"
        settlementMethodLabel="Manual"
        acknowledgmentLabel="I confirm this refund has been paid out."
        canSettle
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />
    );
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
