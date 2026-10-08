import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PaymentExpiredState } from "./PaymentExpiredState";

// FVS-027-IMPLEMENTATION-PLAN.md T06 — kept distinct from Failed; no
// claimed provider-specific reason.

describe("PaymentExpiredState", () => {
  it("renders expired-session copy, distinct from a failure message", () => {
    render(<PaymentExpiredState />);
    expect(screen.getByText(/expired/i)).toBeInTheDocument();
    expect(screen.queryByText(/could not be completed/i)).not.toBeInTheDocument();
  });

  it("renders no CTA at all when actionSlot is omitted — no dead link", () => {
    render(<PaymentExpiredState />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders the supplied actionSlot when given", () => {
    render(<PaymentExpiredState actionSlot={<a href="/cart">Return to cart</a>} />);
    expect(screen.getByRole("link", { name: "Return to cart" })).toBeInTheDocument();
  });

  it("never claims a provider-specific reason", () => {
    render(<PaymentExpiredState />);
    expect(screen.queryByText(/declined|insufficient funds/i)).not.toBeInTheDocument();
  });
});
