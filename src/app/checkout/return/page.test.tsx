import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import CheckoutReturnPage from "./page";

// Minimal FVS-026 -> FVS-027 handoff: the redirect_url target. A return
// is never proof of payment, so the page claims no outcome at all.
describe("CheckoutReturnPage (/checkout/return)", () => {
  it("never claims the payment succeeded, failed or was paid", () => {
    render(<CheckoutReturnPage />);
    expect(screen.getByRole("status")).toHaveTextContent("Your payment hasn't been confirmed yet.");
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/payment (was )?successful|payment (has )?failed|order is paid|has been paid/i);
  });

  it("points to where the confirmation will really arrive", () => {
    render(<CheckoutReturnPage />);
    expect(screen.getByRole("link", { name: "View notifications" })).toHaveAttribute("href", "/account/notifications");
  });

  it("links to the order history, where the order's real status is shown (phase 5E)", () => {
    render(<CheckoutReturnPage />);
    // The return URL carries an order NUMBER, not an id, and is never read:
    // the page links to the history rather than guessing an order page.
    expect(screen.getByRole("link", { name: "View your orders" })).toHaveAttribute("href", "/account/orders");
  });
});
