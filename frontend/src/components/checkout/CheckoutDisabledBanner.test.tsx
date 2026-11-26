import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { CheckoutDisabledBanner } from "./CheckoutDisabledBanner";

// FVS-026-IMPLEMENTATION-PLAN.md T06 — the kill-switch banner. Takes
// only an already-resolved reason string, never a guessed
// acceptingOrders/isCheckoutEnabled settings field name.

describe("CheckoutDisabledBanner", () => {
  it("renders the exact supplied reason as an alert", () => {
    render(<CheckoutDisabledBanner reason="We're not accepting orders right now. Please check back later." />);
    expect(screen.getByRole("alert")).toHaveTextContent("We're not accepting orders right now. Please check back later.");
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<CheckoutDisabledBanner reason="Checkout is temporarily disabled." />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
