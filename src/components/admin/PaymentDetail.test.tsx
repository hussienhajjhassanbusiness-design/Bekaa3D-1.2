import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PaymentDetail } from "./PaymentDetail";
import type { AdminPaymentModel } from "@/lib/admin/adminPaymentModel";

// FVS-028-IMPLEMENTATION-PLAN.md T02 (T03 folded in) — presentational
// only, no network. Renders only confirmed conceptual fields; never
// a raw provider payload/JSON blob viewer. Reconciliation never
// optimistically changes the displayed status.

function makePayment(overrides: Partial<AdminPaymentModel> = {}): AdminPaymentModel {
  return {
    id: "pay-1",
    status: "pending",
    amountCents: 5000,
    currency: "USD",
    providerDisplayLabel: "Whish",
    providerReferenceDisplayValue: "REF-123",
    linkedOrderDisplayId: "ORD-456",
    canManualConfirm: false,
    ...overrides,
  };
}

describe("PaymentDetail", () => {
  it("renders status, amount, provider, and linked order from the normalized model", () => {
    render(<PaymentDetail payment={makePayment()} onReconcile={vi.fn()} />);
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.getByText("$50.00")).toBeInTheDocument();
    expect(screen.getByText("Whish")).toBeInTheDocument();
    expect(screen.getByText("REF-123")).toBeInTheDocument();
    expect(screen.getByText("ORD-456")).toBeInTheDocument();
  });

  it("uses the model's own currency for amount display, never a hardcoded one", () => {
    render(<PaymentDetail payment={makePayment({ amountCents: 1200, currency: "EUR" })} onReconcile={vi.fn()} />);
    expect(screen.getByText("€12.00")).toBeInTheDocument();
  });

  it("renders no raw JSON/payload viewer of any kind", () => {
    const { container } = render(<PaymentDetail payment={makePayment()} onReconcile={vi.fn()} />);
    expect(container.querySelector("pre, code")).toBeNull();
  });

  it("the Reconcile button calls onReconcile with the exact payment id", async () => {
    const onReconcile = vi.fn();
    const user = userEvent.setup();
    render(<PaymentDetail payment={makePayment({ id: "pay-9" })} onReconcile={onReconcile} />);

    await user.click(screen.getByRole("button", { name: /reconcile/i }));

    expect(onReconcile).toHaveBeenCalledWith("pay-9");
  });

  it("disables Reconcile and shows progress text while isReconciling", () => {
    render(<PaymentDetail payment={makePayment()} onReconcile={vi.fn()} isReconciling />);
    expect(screen.getByRole("button", { name: /reconcil/i })).toBeDisabled();
    expect(screen.getByText(/reconciling/i)).toBeInTheDocument();
  });

  it("never optimistically changes the displayed status after clicking Reconcile", async () => {
    const user = userEvent.setup();
    render(<PaymentDetail payment={makePayment({ status: "pending" })} onReconcile={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /reconcile/i }));

    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.queryByText("Paid")).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<PaymentDetail payment={makePayment()} onReconcile={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<PaymentDetail payment={makePayment()} onReconcile={vi.fn()} />);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
