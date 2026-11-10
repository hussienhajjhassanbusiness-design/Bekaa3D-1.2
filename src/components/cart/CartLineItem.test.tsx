import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CartLineItem } from "./CartLineItem";
import type { CartLineModel } from "@/lib/cart/cartModel";

// Presentational only. Every value shown comes from CartLineRead; the
// component never computes a price, a line total, or a cap of its own.

function line(overrides: Partial<CartLineModel> = {}): CartLineModel {
  return {
    productId: "p-1",
    productType: "physical",
    name: "Dragon",
    slug: "dragon",
    coverImage: { src: "http://media/dragon.webp", alt: "A dragon" },
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

function renderLine(overrides: Partial<CartLineModel> = {}, props: Partial<Parameters<typeof CartLineItem>[0]> = {}) {
  const onQuantityChange = vi.fn();
  const onRemove = vi.fn();
  render(<CartLineItem line={line(overrides)} onQuantityChange={onQuantityChange} onRemove={onRemove} {...props} />);
  return { onQuantityChange, onRemove };
}

describe("CartLineItem", () => {
  it("shows the image, the name linking to the product page, the type and the unit price", () => {
    renderLine();
    expect(screen.getByRole("img", { name: "A dragon" })).toHaveAttribute("src", "http://media/dragon.webp");
    expect(screen.getByRole("link", { name: "Dragon" })).toHaveAttribute("href", "/shop/dragon");
    expect(screen.getByText("Physical")).toBeInTheDocument();
    expect(screen.getByText("$25.00")).toBeInTheDocument();
  });

  it("never renders a line total (CartLineRead has none)", () => {
    renderLine({ quantity: 2 });
    expect(screen.queryByText("$50.00")).not.toBeInTheDocument();
  });

  it("renders a plain name, not a link, when the product is no longer listed (slug null)", () => {
    renderLine({ slug: null, purchasable: false, unpurchasableReason: "not_listed", currentPrice: null });
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("Dragon")).toBeInTheDocument();
  });

  it("physical: + sends quantity+1 and − sends quantity−1, as absolute values, by product id", async () => {
    const user = userEvent.setup();
    const { onQuantityChange } = renderLine({ quantity: 2 });
    await user.click(screen.getByRole("button", { name: "Increase quantity of Dragon" }));
    await user.click(screen.getByRole("button", { name: "Decrease quantity of Dragon" }));
    expect(onQuantityChange).toHaveBeenNthCalledWith(1, "p-1", 3);
    expect(onQuantityChange).toHaveBeenNthCalledWith(2, "p-1", 1);
  });

  it("physical: − is disabled at 1 and + is disabled at the server's max_quantity", () => {
    renderLine({ quantity: 1, maxQuantity: 1 });
    expect(screen.getByRole("button", { name: "Decrease quantity of Dragon" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Increase quantity of Dragon" })).toBeDisabled();
    expect(screen.getByText("Maximum 1 per order")).toBeInTheDocument();
  });

  it("STL: no stepper at all, quantity fixed at 1 with an explanation", () => {
    renderLine({ productType: "stl", quantity: 1, maxQuantity: null, name: "Dragon STL" });
    expect(screen.queryByRole("button", { name: /quantity/i })).not.toBeInTheDocument();
    expect(screen.getByText("STL")).toBeInTheDocument();
    expect(screen.getByText(/one copy per order/i)).toBeInTheDocument();
  });

  it("price changed: shows both the price when added and the current price, never silently swapping", () => {
    renderLine({ priceChanged: true, currentPrice: { amountCents: 3000, currency: "USD" } });
    expect(screen.getByText("$25.00")).toBeInTheDocument();
    expect(screen.getByText("$30.00")).toBeInTheDocument();
    expect(screen.getByText(/price has changed since you added it/i)).toBeInTheDocument();
  });

  it.each([
    ["unavailable", /currently unavailable/i],
    ["whatsapp_only", /only be ordered through WhatsApp/i],
    ["not_listed", /no longer available/i],
  ] as const)("unpurchasable (%s): explains why, offers no stepper, keeps Remove", (reason, copy) => {
    renderLine({ purchasable: false, unpurchasableReason: reason });
    expect(screen.getByText(copy)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /quantity/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Dragon from cart" })).toBeEnabled();
  });

  it("over cap: explains the new cap, disables +, and offers reduce-to-cap", async () => {
    const user = userEvent.setup();
    const { onQuantityChange } = renderLine({ quantity: 8, maxQuantity: 3, overCap: true });
    expect(screen.getByText(/at most 3 of this product per order now/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Increase quantity of Dragon" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Reduce Dragon to 3" }));
    expect(onQuantityChange).toHaveBeenCalledWith("p-1", 3);
  });

  it("Remove sends the product id", async () => {
    const user = userEvent.setup();
    const { onRemove } = renderLine();
    await user.click(screen.getByRole("button", { name: "Remove Dragon from cart" }));
    expect(onRemove).toHaveBeenCalledWith("p-1");
  });

  it("while pending: every control is disabled and the line is marked busy", () => {
    renderLine({}, { pending: true });
    for (const button of screen.getAllByRole("button")) {
      expect(button).toBeDisabled();
    }
    expect(screen.getByRole("article")).toHaveAttribute("aria-busy", "true");
  });

  it("shows a line error as an alert", () => {
    renderLine({}, { errorMessage: "That quantity is above the limit for this product." });
    expect(screen.getByRole("alert")).toHaveTextContent("That quantity is above the limit for this product.");
  });

  it("uses a neutral placeholder and fallback name when the product row is gone", () => {
    renderLine({ name: null, coverImage: null, slug: null, purchasable: false, unpurchasableReason: "not_listed" });
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("Product no longer available")).toBeInTheDocument();
  });
});
