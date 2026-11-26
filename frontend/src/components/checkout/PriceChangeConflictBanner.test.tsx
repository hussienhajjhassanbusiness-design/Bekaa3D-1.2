import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PriceChangeConflictBanner } from "./PriceChangeConflictBanner";
import type { PriceChangeLine } from "@/lib/checkout/checkoutErrors";

// #SECURITY-CHECKOUT-PRICE-CONFIRMATION — built from the 409
// CART_PRICE_CHANGED `price_changes` extension. Nothing is accepted
// automatically: onAccept fires only on an explicit click.

const CHANGES: PriceChangeLine[] = [
  {
    productId: "p-1",
    oldAmountCents: 1000,
    newAmountCents: 1200,
    currency: "USD",
  },
  {
    productId: "p-gone",
    oldAmountCents: 500,
    newAmountCents: 400,
    currency: "USD",
  },
];
const NAMES = { "p-1": "Garden Gnome" };

describe("PriceChangeConflictBanner", () => {
  it("is an assertive alert naming each changed line with its old and new price", () => {
    render(<PriceChangeConflictBanner changes={CHANGES} names={NAMES} accepted={false} onAccept={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveAttribute("aria-live", "assertive");
    expect(screen.getByText("Garden Gnome")).toBeInTheDocument();
    expect(screen.getByText("$10.00")).toBeInTheDocument();
    expect(screen.getByText("$12.00")).toBeInTheDocument();
    // A product no longer in the cart still gets a readable row.
    expect(screen.getByText("A product in your cart")).toBeInTheDocument();
  });

  it("never calls onAccept by itself; calls it once on an explicit click", async () => {
    const onAccept = vi.fn();
    render(<PriceChangeConflictBanner changes={CHANGES} names={NAMES} accepted={false} onAccept={onAccept} />);
    expect(onAccept).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Accept new prices" }));
    expect(onAccept).toHaveBeenCalledTimes(1);
  });

  it("after acceptance it says so and asks the customer to place the order", () => {
    render(<PriceChangeConflictBanner changes={CHANGES} names={NAMES} accepted onAccept={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Accept new prices" })).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "You've accepted the new prices. Place your order to continue."
    );
  });

  // Redesign Batch 6.
  it("labels the old and new prices with visible text (Was / Now)", () => {
    render(<PriceChangeConflictBanner changes={CHANGES} names={NAMES} accepted={false} onAccept={vi.fn()} />);
    expect(screen.getAllByText("Was")).toHaveLength(2);
    expect(screen.getAllByText("Now")).toHaveLength(2);
  });
});
