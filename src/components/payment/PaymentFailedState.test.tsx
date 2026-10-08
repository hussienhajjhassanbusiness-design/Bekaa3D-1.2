import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PaymentFailedState } from "./PaymentFailedState";

// FVS-027-IMPLEMENTATION-PLAN.md T06 — safe retry guidance only, no
// invented working Checkout/Cart link.

describe("PaymentFailedState", () => {
  it("renders safe failure copy", () => {
    render(<PaymentFailedState />);
    expect(screen.getByText(/payment could not be completed/i)).toBeInTheDocument();
  });

  it("renders no CTA at all when actionSlot is omitted — no dead link", () => {
    render(<PaymentFailedState />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders the supplied actionSlot when given", () => {
    render(<PaymentFailedState actionSlot={<a href="/cart">Return to cart</a>} />);
    expect(screen.getByRole("link", { name: "Return to cart" })).toBeInTheDocument();
  });

  it("never claims a provider-specific failure reason", () => {
    render(<PaymentFailedState />);
    expect(screen.queryByText(/declined|insufficient funds/i)).not.toBeInTheDocument();
  });
});
