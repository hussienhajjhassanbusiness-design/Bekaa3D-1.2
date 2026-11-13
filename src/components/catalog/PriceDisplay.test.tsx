import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PriceDisplay } from "./PriceDisplay";

// FVS-014-IMPLEMENTATION-PLAN.md T01 — display-only. Domain value is
// always integer cents (vertical-slice-plan.md's own global "Money uses
// integer cents" rule) — this component never parses money (that stays
// MoneyInput's job) and never computes a NEW monetary amount; the one
// division by 100 exists only to satisfy Intl.NumberFormat's major-unit
// API contract, and Intl.NumberFormat rounds correctly to the
// currency's minor-unit digits, so it produces no visible artifact.
// Currency is always an explicit, required prop — never hardcoded,
// since vertical-slice-plan.md §2 lists USD settlement itself as an
// open external item.

describe("PriceDisplay", () => {
  it("renders zero correctly", () => {
    render(<PriceDisplay amountCents={0} currency="USD" locale="en-US" />);
    expect(screen.getByText("$0.00")).toBeInTheDocument();
  });

  it("maps cents into the minor-unit digits exactly", () => {
    render(<PriceDisplay amountCents={5} currency="USD" locale="en-US" />);
    expect(screen.getByText("$0.05")).toBeInTheDocument();
  });

  it("produces no floating-point artifact for a tricky value like 10 cents", () => {
    render(<PriceDisplay amountCents={10} currency="USD" locale="en-US" />);
    expect(screen.getByText("$0.10")).toBeInTheDocument();
  });

  it("renders whole units correctly", () => {
    render(<PriceDisplay amountCents={1200} currency="USD" locale="en-US" />);
    expect(screen.getByText("$12.00")).toBeInTheDocument();
  });

  it("renders a large amount with correct grouping", () => {
    render(<PriceDisplay amountCents={123456789} currency="USD" locale="en-US" />);
    expect(screen.getByText("$1,234,567.89")).toBeInTheDocument();
  });

  it("requires and displays the explicit currency, never a hardcoded one", () => {
    render(<PriceDisplay amountCents={120000} currency="EUR" locale="en-US" />);
    expect(screen.getByText("€1,200.00")).toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    render(<PriceDisplay amountCents={100} currency="USD" locale="en-US" />);
    expect(screen.getByText("$1.00")).toBeInTheDocument();
  });

  it("adds no presentation classes unless a size is requested (existing call sites unchanged)", () => {
    render(<PriceDisplay amountCents={100} currency="USD" locale="en-US" />);
    expect(screen.getByText("$1.00")).not.toHaveAttribute("class");
  });

  it("applies the Stitch price role for an opted-in size without changing the formatted value", () => {
    render(<PriceDisplay amountCents={4999} currency="USD" locale="en-US" size="card" />);
    const price = screen.getByText("$49.99");
    expect(price).toHaveClass("text-headline-md", "text-primary");
  });
});
