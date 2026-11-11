import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AdminOrderSummaryDisplay } from "./AdminOrderSummaryDisplay";

// FVS-030-IMPLEMENTATION-PLAN.md T06 — extracted from OrderDetail's
// own existing summary block (its own prior inline JSX). A second
// genuine reuse case (AdminOrderDetail) justifies this now, mirroring
// this engagement's established extraction pattern.

describe("AdminOrderSummaryDisplay", () => {
  it("renders only the present summary fields, omitting absent ones", () => {
    render(<AdminOrderSummaryDisplay summary={{ currency: "USD" }} />);
    expect(screen.queryByText(/total/i)).not.toBeInTheDocument();
  });

  it("renders the total when present", () => {
    render(<AdminOrderSummaryDisplay summary={{ currency: "USD", totalCents: 2499 }} />);
    expect(screen.getByText("$24.99")).toBeInTheDocument();
  });

  it("renders payment and refund labels when present", () => {
    render(
      <AdminOrderSummaryDisplay summary={{ currency: "USD", paymentStatusLabel: "Paid", refundStatusLabel: "None" }} />
    );
    expect(screen.getByText("Paid")).toBeInTheDocument();
    expect(screen.getByText("None")).toBeInTheDocument();
  });

  it("renders no shipping row — ADR-024 means nothing is ever charged for shipping on this site", () => {
    render(<AdminOrderSummaryDisplay summary={{ currency: "USD", subtotalCents: 1000, totalCents: 1000 }} />);
    expect(screen.queryByText(/shipping/i)).not.toBeInTheDocument();
  });
});
