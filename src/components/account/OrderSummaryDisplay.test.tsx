import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { OrderSummaryDisplay } from "./OrderSummaryDisplay";

// FVS-030-IMPLEMENTATION-PLAN.md T06 — extracted from OrderDetail's
// own existing summary block (its own prior inline JSX). A second
// genuine reuse case (AdminOrderDetail) justifies this now, mirroring
// this engagement's established extraction pattern.

describe("OrderSummaryDisplay", () => {
  it("renders only the present summary fields, omitting absent ones", () => {
    render(<OrderSummaryDisplay summary={{ currency: "USD" }} />);
    expect(screen.queryByText(/total/i)).not.toBeInTheDocument();
  });

  it("renders the total when present", () => {
    render(<OrderSummaryDisplay summary={{ currency: "USD", totalCents: 2499 }} />);
    expect(screen.getByText("$24.99")).toBeInTheDocument();
  });

  it("renders payment and refund labels when present", () => {
    render(
      <OrderSummaryDisplay summary={{ currency: "USD", paymentStatusLabel: "Paid", refundStatusLabel: "None" }} />
    );
    expect(screen.getByText("Paid")).toBeInTheDocument();
    expect(screen.getByText("None")).toBeInTheDocument();
  });
});
