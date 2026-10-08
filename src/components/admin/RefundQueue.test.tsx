import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RefundQueue } from "./RefundQueue";
import type { RefundModel } from "@/lib/admin/refundModel";

// FVS-032-IMPLEMENTATION-PLAN.md T06 — composes the existing, fully
// generic AdminTable directly (#SHARED-ADMIN-TABLE), mirroring
// AdminPaymentList's exact structure (evidence-tier decision, §0 of
// the plan). Every value is plain/non-clickable — no admin
// refund-detail route exists yet to link to.

const REFUNDS: readonly RefundModel[] = [
  {
    id: "refund-1",
    linkedOrderDisplayId: "ORD-456",
    statusLabel: "Pending settlement",
    isSettled: false,
    totalAmountCents: 2000,
    currency: "USD",
    settlementMethodLabel: "Manual",
  },
];

describe("RefundQueue", () => {
  it("renders every row's normalized fields via the shared components", () => {
    render(<RefundQueue refunds={REFUNDS} />);
    expect(screen.getByText("Pending settlement")).toBeInTheDocument();
    expect(screen.getByText("$20.00")).toBeInTheDocument();
    expect(screen.getByText("Manual")).toBeInTheDocument();
    expect(screen.getByText("ORD-456")).toBeInTheDocument();
  });

  it("renders no clickable link anywhere in the table", () => {
    render(<RefundQueue refunds={REFUNDS} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("the View trigger calls onSelectRefund with the exact refund id, never a navigation", async () => {
    const onSelectRefund = vi.fn();
    const user = userEvent.setup();
    render(<RefundQueue refunds={REFUNDS} onSelectRefund={onSelectRefund} />);

    await user.click(screen.getByRole("button", { name: /view/i }));

    expect(onSelectRefund).toHaveBeenCalledWith("refund-1");
  });

  it("renders no View trigger when onSelectRefund is not supplied", () => {
    render(<RefundQueue refunds={REFUNDS} />);
    expect(screen.queryByRole("button", { name: /view/i })).not.toBeInTheDocument();
  });

  it("delegates the empty state to AdminTable", () => {
    render(<RefundQueue refunds={[]} />);
    expect(screen.getByText(/no results found/i)).toBeInTheDocument();
  });

  it("gives a pending refund a different tone than a settled one, driven by isSettled", () => {
    render(
      <RefundQueue
        refunds={[
          REFUNDS[0]!,
          { ...REFUNDS[0]!, id: "refund-2", isSettled: true, statusLabel: "Settled" },
        ]}
      />
    );
    const badges = document.querySelectorAll("tbody span");
    const classNames = Array.from(badges).map((badge) => badge.className);
    expect(new Set(classNames).size).toBeGreaterThan(1);
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<RefundQueue refunds={REFUNDS} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
