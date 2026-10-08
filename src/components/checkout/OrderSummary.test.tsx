import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { OrderSummary } from "./OrderSummary";

// FVS-026-IMPLEMENTATION-PLAN.md T07 — #SECURITY-SERVER-CHECKOUT-TOTALS.
// Display-only: every amount field is optional, and this component
// NEVER sums/infers one field from the others.

describe("OrderSummary", () => {
  it("renders every supplied amount via PriceDisplay with the exact given currency", () => {
    render(<OrderSummary subtotalCents={1000} shippingCents={500} totalCents={1500} currency="USD" />);
    expect(screen.getByText("$10.00")).toBeInTheDocument();
    expect(screen.getByText("$5.00")).toBeInTheDocument();
    expect(screen.getByText("$15.00")).toBeInTheDocument();
  });

  it("never computes or infers an omitted field from the others", () => {
    render(<OrderSummary subtotalCents={1000} shippingCents={500} currency="USD" />);
    // totalCents was NOT supplied — must never show a computed $15.00.
    expect(screen.queryByText("$15.00")).not.toBeInTheDocument();
  });

  it("renders a placeholder when no amount field is supplied at all — never fabricated zeros", () => {
    render(<OrderSummary currency="USD" />);
    expect(screen.getByText(/confirmed at submission/i)).toBeInTheDocument();
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
  });

  it("renders only the subtotal when that is the only field supplied", () => {
    render(<OrderSummary subtotalCents={1000} currency="USD" />);
    expect(screen.getByText("$10.00")).toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<OrderSummary subtotalCents={1000} currency="USD" />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
