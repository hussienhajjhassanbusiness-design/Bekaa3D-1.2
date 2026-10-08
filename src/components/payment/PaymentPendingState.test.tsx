import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PaymentPendingState } from "./PaymentPendingState";

// FVS-027-IMPLEMENTATION-PLAN.md T04 — honest copy only. No fake
// percentage/progress bar; a spinner never implies a measurable
// fraction of completion or that the provider has already approved
// anything.

describe("PaymentPendingState", () => {
  it("renders honest confirming-payment copy", () => {
    render(<PaymentPendingState />);
    expect(screen.getByText(/confirming your payment/i)).toBeInTheDocument();
  });

  it("renders no numeric/percentage progress indicator of any kind", () => {
    render(<PaymentPendingState />);
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("never implies the provider has approved anything", () => {
    render(<PaymentPendingState />);
    expect(screen.queryByText(/approved|successful|complete/i)).not.toBeInTheDocument();
  });

  it("spinner respects prefers-reduced-motion", () => {
    const { container } = render(<PaymentPendingState />);
    const spinner = container.querySelector(".animate-spin, .animate-pulse");
    expect(spinner?.getAttribute("class")).toMatch(/motion-reduce:/);
  });
});
