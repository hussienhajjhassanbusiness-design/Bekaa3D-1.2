import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { RefundDetail } from "./RefundDetail";
import type { RefundModel } from "@/lib/admin/refundModel";

// FVS-032-IMPLEMENTATION-PLAN.md T05 — admin-facing operational
// presentation only. No provider secret/raw webhook payload field
// exists on RefundModel, so none can be rendered here structurally.
// Pending settlement is visually distinct from settled via the
// explicit `isSettled` capability, never inferred from statusLabel
// text (#SECURITY-REFUND-SETTLEMENT-SEPARATION).

function makeRefund(overrides: Partial<RefundModel> = {}): RefundModel {
  return {
    id: "refund-1",
    linkedOrderDisplayId: "order-1",
    statusLabel: "Pending settlement",
    isSettled: false,
    totalAmountCents: 2000,
    currency: "USD",
    ...overrides,
  };
}

describe("RefundDetail", () => {
  it("renders the refund id, linked order, and status label", () => {
    render(<RefundDetail refund={makeRefund()} />);
    expect(screen.getByText(/refund-1/)).toBeInTheDocument();
    expect(screen.getByText(/order-1/)).toBeInTheDocument();
    expect(screen.getByText("Pending settlement")).toBeInTheDocument();
  });

  it("renders the total amount via PriceDisplay", () => {
    render(<RefundDetail refund={makeRefund()} />);
    expect(screen.getByText("$20.00")).toBeInTheDocument();
  });

  it("gives a pending refund a visually distinct tone from a settled one, driven by isSettled", () => {
    const { container: pending } = render(<RefundDetail refund={makeRefund({ isSettled: false })} />);
    const { container: settled } = render(
      <RefundDetail refund={makeRefund({ isSettled: true, statusLabel: "Settled" })} />
    );
    const pendingBadge = pending.querySelector("span");
    const settledBadge = settled.querySelector("span");
    expect(pendingBadge?.className).not.toBe(settledBadge?.className);
  });

  it("renders the settlement method label when present", () => {
    render(<RefundDetail refund={makeRefund({ settlementMethodLabel: "Manual" })} />);
    expect(screen.getByText("Manual")).toBeInTheDocument();
  });

  it("renders no settlement method when absent", () => {
    render(<RefundDetail refund={makeRefund()} />);
    expect(screen.queryByText("Manual")).not.toBeInTheDocument();
  });

  it("renders the per-line breakdown when present, reusing PriceDisplay", () => {
    render(
      <RefundDetail
        refund={makeRefund({
          lines: [{ lineId: "line-1", productDisplayName: "Garden Gnome", amountCents: 1500, currency: "USD" }],
        })}
      />
    );
    expect(screen.getByText("Garden Gnome")).toBeInTheDocument();
    expect(screen.getByText("$15.00")).toBeInTheDocument();
  });

  it("renders no shipping row — ADR-024 means nothing was ever charged for shipping", () => {
    render(<RefundDetail refund={makeRefund()} />);
    expect(screen.queryByText(/shipping/i)).not.toBeInTheDocument();
  });

  it("renders the reason when present", () => {
    render(<RefundDetail refund={makeRefund({ reason: "Damaged in transit" })} />);
    expect(screen.getByText("Damaged in transit")).toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<RefundDetail refund={makeRefund()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
