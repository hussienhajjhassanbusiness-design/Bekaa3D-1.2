import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { CheckoutStepper } from "./CheckoutStepper";

// FVS-026-IMPLEMENTATION-PLAN.md T03 — a semantic progress indicator,
// not an interactive wizard. Checkout is a single page with all
// sections visible simultaneously (so a price-conflict banner is
// never hidden behind a step transition); this component only
// orients the user within that one page.

describe("CheckoutStepper", () => {
  it("renders the three sections in order", () => {
    render(<CheckoutStepper currentSection="delivery" />);
    const items = screen.getAllByRole("listitem");
    expect(items.map((el) => el.textContent)).toEqual(["Delivery", "Review", "Confirm"]);
  });

  it("marks the current section with aria-current, and no other section", () => {
    render(<CheckoutStepper currentSection="review" />);
    expect(screen.getByText("Review")).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("Delivery")).not.toHaveAttribute("aria-current");
    expect(screen.getByText("Confirm")).not.toHaveAttribute("aria-current");
  });

  it("renders no interactive controls of its own — a progress indicator, not a wizard", () => {
    render(<CheckoutStepper currentSection="confirm" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("is a labeled navigation landmark", () => {
    render(<CheckoutStepper currentSection="delivery" />);
    expect(screen.getByRole("navigation", { name: /checkout progress/i })).toBeInTheDocument();
  });
});
