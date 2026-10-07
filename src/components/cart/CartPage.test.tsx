import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CartPage } from "./CartPage";
import type { CartModel } from "@/lib/cart/cartModel";

// FVS-025-IMPLEMENTATION-PLAN.md T05 — presentational only, not
// mounted to a route (T09 blocked). No summary/totals area is built
// (no confirmed cart-read totals concept); no Checkout link/button
// anywhere (/checkout doesn't exist yet — the dead-link rule applies
// exactly as in FVS-022).

const CART: CartModel = {
  id: "cart-1",
  lines: [
    { id: "line-1", productId: "prod-1", productDisplayName: "Garden Gnome", productType: "physical", quantity: 2, snapshotPriceCents: 1999, currency: "USD" },
    { id: "line-2", productId: "prod-2", productDisplayName: "Dragon STL", productType: "stl", quantity: 1, snapshotPriceCents: 500, currency: "USD" },
  ],
};

describe("CartPage", () => {
  it("shows a loading state", () => {
    render(<CartPage cart={null} isLoading onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows a safe error message with a retry action", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(
      <CartPage cart={null} isError errorMessage="Couldn't load your cart." onRetry={onRetry} onQuantityChange={vi.fn()} onRemove={vi.fn()} />
    );

    expect(screen.getByText("Couldn't load your cart.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows a safe empty-cart message — no fake recommendations", () => {
    render(<CartPage cart={{ id: "cart-1", lines: [] }} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.getByText(/cart is empty/i)).toBeInTheDocument();
  });

  it("renders every line", () => {
    render(<CartPage cart={CART} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.getByText("Garden Gnome")).toBeInTheDocument();
    expect(screen.getByText("Dragon STL")).toBeInTheDocument();
  });

  it("renders no Checkout link or button anywhere — /checkout doesn't exist yet", () => {
    render(<CartPage cart={CART} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.queryByRole("link", { name: /checkout/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /checkout/i })).not.toBeInTheDocument();
  });

  it("renders no summary/totals area — no confirmed cart-read totals concept", () => {
    render(<CartPage cart={CART} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.queryByText(/subtotal/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^total$/i)).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<CartPage cart={CART} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<CartPage cart={CART} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
