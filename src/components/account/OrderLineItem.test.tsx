import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { OrderLineItem } from "./OrderLineItem";
import type { OrderLineModel } from "@/lib/orders/orderModel";

// FVS-029-IMPLEMENTATION-PLAN.md T03 — the customer-visible shared
// primitive FVS-030 must compose around, never modify to add admin
// fields (#ARCHITECTURE-CUSTOMER-ADMIN-ORDER-BOUNDARY). Renders only
// supplied immutable snapshot data — never a product link, never
// substitutes a "current price" for the snapshot.

function makePhysicalLine(overrides: Partial<OrderLineModel> = {}): OrderLineModel {
  return {
    id: "line-1",
    productDisplayName: "Garden Gnome",
    productType: "physical",
    quantity: 2,
    unitPriceCents: 1999,
    lineTotalCents: 3998,
    currency: "USD",
    statusLabel: "Processing",
    ...overrides,
  };
}

function makeStlLine(overrides: Partial<OrderLineModel> = {}): OrderLineModel {
  return {
    id: "line-2",
    productDisplayName: "Dragon STL",
    productType: "stl",
    quantity: 1,
    unitPriceCents: 500,
    lineTotalCents: 500,
    currency: "USD",
    statusLabel: "Delivered",
    ...overrides,
  };
}

describe("OrderLineItem", () => {
  it("renders the exact supplied product name, quantity, price, and status", () => {
    render(<OrderLineItem line={makePhysicalLine()} />);
    expect(screen.getByText("Garden Gnome")).toBeInTheDocument();
    expect(screen.getByText(/2/)).toBeInTheDocument();
    expect(screen.getByText("$39.98")).toBeInTheDocument();
    expect(screen.getByText("Processing")).toBeInTheDocument();
  });

  it("renders a physical line and an STL line independently with their own status", () => {
    render(
      <>
        <OrderLineItem line={makePhysicalLine()} />
        <OrderLineItem line={makeStlLine()} />
      </>
    );
    expect(screen.getByText("Garden Gnome")).toBeInTheDocument();
    expect(screen.getByText("Dragon STL")).toBeInTheDocument();
    expect(screen.getByText("Processing")).toBeInTheDocument();
    expect(screen.getByText("Delivered")).toBeInTheDocument();
  });

  it("renders the status as visible text via StatusBadge, never color-only", () => {
    render(<OrderLineItem line={makePhysicalLine({ statusLabel: "Shipped" })} />);
    expect(screen.getByText("Shipped")).toBeInTheDocument();
  });

  it("has no way to render a product link — no such prop exists on this type", () => {
    render(<OrderLineItem line={makePhysicalLine()} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("has no internal-note prop or render path — structurally impossible given its type", () => {
    render(<OrderLineItem line={makePhysicalLine()} />);
    expect(screen.queryByText(/internal/i)).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<OrderLineItem line={makePhysicalLine()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
