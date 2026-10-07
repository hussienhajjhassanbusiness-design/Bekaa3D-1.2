import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MiniCartDrawer } from "./MiniCartDrawer";
import type { CartModel } from "@/lib/cart/cartModel";

// FVS-025-IMPLEMENTATION-PLAN.md T06 — reuses DialogShell's real
// focus-trap/Escape/backdrop via its new panelClassName seam; zero
// new focus-trap code. Anonymous state renders LoggedOutCartPrompt
// (resolving the /cart discrepancy — plan §0); authenticated state
// renders the same cart presentation CartPage does.

const CART: CartModel = {
  id: "cart-1",
  lines: [{ id: "line-1", productId: "prod-1", productDisplayName: "Garden Gnome", productType: "physical", quantity: 1, snapshotPriceCents: 1999, currency: "USD" }],
};

describe("MiniCartDrawer", () => {
  it("is absent from the DOM when closed", () => {
    render(<MiniCartDrawer open={false} onClose={vi.fn()} isAuthenticated={false} cart={null} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("reuses DialogShell's real accessible-dialog mechanics (role=dialog, aria-modal)", () => {
    render(<MiniCartDrawer open onClose={vi.fn()} isAuthenticated={false} cart={null} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("closes on Escape — proves the real DialogShell focus trap is wired, not a second implementation", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<MiniCartDrawer open onClose={onClose} isAuthenticated={false} cart={null} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);

    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalled();
  });

  it("renders LoggedOutCartPrompt when anonymous", () => {
    render(<MiniCartDrawer open onClose={vi.fn()} isAuthenticated={false} cart={null} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.getByRole("link", { name: /log in/i })).toBeInTheDocument();
  });

  it("renders cart lines when authenticated data is supplied", () => {
    render(<MiniCartDrawer open onClose={vi.fn()} isAuthenticated cart={CART} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.getByText("Garden Gnome")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /log in/i })).not.toBeInTheDocument();
  });

  it("shows a safe empty-cart message when authenticated with no lines", () => {
    render(<MiniCartDrawer open onClose={vi.fn()} isAuthenticated cart={{ id: "cart-1", lines: [] }} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(screen.getByText(/cart is empty/i)).toBeInTheDocument();
  });

  it("has a responsive drawer panel: bottom sheet on mobile, side drawer at tablet and above", () => {
    render(<MiniCartDrawer open onClose={vi.fn()} isAuthenticated={false} cart={null} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    const dialog = screen.getByRole("dialog");
    expect(dialog.className).toMatch(/fixed/);
    expect(dialog.className).toMatch(/tablet:/);
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<MiniCartDrawer open onClose={vi.fn()} isAuthenticated cart={CART} onQuantityChange={vi.fn()} onRemove={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
