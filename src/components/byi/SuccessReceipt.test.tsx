import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SuccessReceipt } from "./SuccessReceipt";

// FVS-015-IMPLEMENTATION-PLAN.md T02 — safe generic confirmation only.
// No internal database id, storage key, attachment URL, captcha proof,
// or internal status is ever exposed — none of that is a backend-
// confirmed public-safe field yet.

describe("SuccessReceipt", () => {
  it("renders a safe default confirmation message", () => {
    render(<SuccessReceipt />);
    expect(screen.getByText(/thanks/i)).toBeInTheDocument();
  });

  it("supports a custom message", () => {
    render(<SuccessReceipt message="We received your submission." />);
    expect(screen.getByText("We received your submission.")).toBeInTheDocument();
  });

  it("exposes the confirmation as an announced status region", () => {
    render(<SuccessReceipt />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
