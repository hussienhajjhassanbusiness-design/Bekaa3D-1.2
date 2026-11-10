import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CartPage, type CartPageProps } from "./CartPage";
import type { CartLineModel, CartModel } from "@/lib/cart/cartModel";

function line(overrides: Partial<CartLineModel> = {}): CartLineModel {
  return {
    productId: "p-1",
    productType: "physical",
    name: "Dragon",
    slug: "dragon",
    coverImage: null,
    quantity: 2,
    snapshotPrice: { amountCents: 2500, currency: "USD" },
    currentPrice: { amountCents: 2500, currency: "USD" },
    priceChanged: false,
    maxQuantity: 5,
    overCap: false,
    purchasable: true,
    unpurchasableReason: null,
    ...overrides,
  };
}

function cart(lines: CartLineModel[]): CartModel {
  return {
    id: lines.length ? "c-1" : null,
    lines,
    containsPhysical: lines.some((l) => l.productType === "physical"),
    containsDigital: lines.some((l) => l.productType === "stl"),
    updatedAt: null,
  };
}

function renderPage(props: Partial<CartPageProps> = {}) {
  const handlers = { onQuantityChange: vi.fn(), onRemove: vi.fn(), onRetry: vi.fn() };
  render(<CartPage cart={null} {...handlers} {...props} />);
  return handlers;
}

describe("CartPage", () => {
  it("loading: an accessible status with skeleton blocks", () => {
    renderPage({ isLoading: true });
    expect(screen.getByRole("status")).toHaveTextContent("Loading your cart");
  });

  it("error: a retryable alert", async () => {
    const user = userEvent.setup();
    const { onRetry } = renderPage({ isError: true });
    expect(screen.getByRole("alert")).toHaveTextContent("We couldn't load your cart");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("empty (never-written cart): explains and links to the shop", () => {
    renderPage({ cart: cart([]) });
    expect(screen.getByText("Your cart is empty.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse the shop" })).toHaveAttribute("href", "/shop");
  });

  it("populated: one list item per line in the server's order", () => {
    renderPage({ cart: cart([line(), line({ productId: "p-2", name: "Knight", productType: "stl", quantity: 1, maxQuantity: null })]) });
    const items = within(screen.getByRole("list", { name: "Cart items" })).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Dragon");
    expect(items[1]).toHaveTextContent("Knight");
  });

  it("summary: an item count, an honest note that totals are set at checkout, and no invented money", () => {
    renderPage({ cart: cart([line({ quantity: 2 }), line({ productId: "p-2", quantity: 1 })]) });
    const summary = screen.getByRole("region", { name: "Cart summary" });
    expect(summary).toHaveTextContent("3 items");
    expect(summary).toHaveTextContent(/total is calculated at checkout from current prices/i);
    expect(summary).not.toHaveTextContent("$");
    expect(summary).not.toHaveTextContent(/shipping|tax|discount/i);
  });

  it("checkout: a truthful state, never a link to a route that does not exist", () => {
    renderPage({ cart: cart([line()]) });
    expect(screen.queryByRole("link", { name: /checkout/i })).not.toBeInTheDocument();
    expect(screen.getByText(/checkout isn't available yet/i)).toBeInTheDocument();
  });

  it("warns when a line needs attention before checkout", () => {
    renderPage({ cart: cart([line({ purchasable: false, unpurchasableReason: "unavailable" })]) });
    expect(screen.getByText(/some items need your attention/i)).toBeInTheDocument();
  });

  it("passes pending state and line errors to the right line", () => {
    renderPage({
      cart: cart([line(), line({ productId: "p-2", name: "Knight" })]),
      pendingProductIds: new Set(["p-2"]),
      lineErrors: { "p-1": "Too many cart changes." },
    });
    const [first, second] = screen.getAllByRole("article");
    expect(first).toHaveAttribute("aria-busy", "false");
    expect(within(first!).getByRole("alert")).toHaveTextContent("Too many cart changes.");
    expect(second).toHaveAttribute("aria-busy", "true");
  });

  it("shows an error for a line that has since disappeared at the top of the page", () => {
    renderPage({ cart: cart([line()]), lineErrors: { "gone-1": "This item is no longer in your cart." } });
    expect(screen.getByRole("alert")).toHaveTextContent("This item is no longer in your cart.");
  });

  it("shows a page notice (e.g. email verification) when given one", () => {
    renderPage({ cart: cart([]), notice: "Verify your email address to add or change items in your cart." });
    expect(screen.getByText(/verify your email address/i)).toBeInTheDocument();
  });
});
