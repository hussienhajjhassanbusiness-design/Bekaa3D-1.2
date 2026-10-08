import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AdminPaymentList } from "./AdminPaymentList";
import type { AdminPaymentModel } from "@/lib/admin/adminPaymentModel";

// FVS-028-IMPLEMENTATION-PLAN.md T05 — composes the existing, fully
// generic AdminTable directly (#SHARED-ADMIN-TABLE), no second table
// implementation. Every value is plain/non-clickable -- no admin
// order/payment-detail route exists yet to link to.

const PAYMENTS: readonly AdminPaymentModel[] = [
  {
    id: "pay-1",
    status: "paid",
    amountCents: 5000,
    currency: "USD",
    providerDisplayLabel: "Whish",
    providerReferenceDisplayValue: "REF-123",
    linkedOrderDisplayId: "ORD-456",
    canManualConfirm: false,
  },
];

describe("AdminPaymentList", () => {
  it("renders every row's normalized fields via the shared components", () => {
    render(<AdminPaymentList payments={PAYMENTS} />);
    expect(screen.getByText("Paid")).toBeInTheDocument();
    expect(screen.getByText("$50.00")).toBeInTheDocument();
    expect(screen.getByText("Whish")).toBeInTheDocument();
    expect(screen.getByText("REF-123")).toBeInTheDocument();
    expect(screen.getByText("ORD-456")).toBeInTheDocument();
  });

  it("renders no clickable link anywhere in the table", () => {
    render(<AdminPaymentList payments={PAYMENTS} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("the View trigger calls onSelectPayment with the exact payment id, never a navigation", async () => {
    const onSelectPayment = vi.fn();
    const user = userEvent.setup();
    render(<AdminPaymentList payments={PAYMENTS} onSelectPayment={onSelectPayment} />);

    await user.click(screen.getByRole("button", { name: /view/i }));

    expect(onSelectPayment).toHaveBeenCalledWith("pay-1");
  });

  it("renders no View trigger when onSelectPayment is not supplied", () => {
    render(<AdminPaymentList payments={PAYMENTS} />);
    expect(screen.queryByRole("button", { name: /view/i })).not.toBeInTheDocument();
  });

  it("delegates the empty state to AdminTable", () => {
    render(<AdminPaymentList payments={[]} />);
    expect(screen.getByText(/no results found/i)).toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<AdminPaymentList payments={PAYMENTS} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<AdminPaymentList payments={PAYMENTS} />);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
