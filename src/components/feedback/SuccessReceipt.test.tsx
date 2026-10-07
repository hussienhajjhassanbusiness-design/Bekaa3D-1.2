import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SuccessReceipt } from "./SuccessReceipt";

// FVS-016-IMPLEMENTATION-PLAN.md T03 — generalized from FVS-015's own
// BYI-flavored component (moved here from src/components/byi/, no
// default message baked in — every caller supplies its own exact,
// backend-contract-free copy). No internal database id, storage key,
// attachment URL, captcha proof, or internal status is ever exposed —
// none of that is a backend-confirmed public-safe field yet, for either
// BYI or Contact.

describe("SuccessReceipt", () => {
  it("renders the supplied message, with no BYI/Contact-specific default baked in", () => {
    render(<SuccessReceipt message="Thanks! We've received your idea and will be in touch soon." />);
    expect(screen.getByText("Thanks! We've received your idea and will be in touch soon.")).toBeInTheDocument();
  });

  it("works equally for a different caller's own copy (proving it is genuinely generic)", () => {
    render(<SuccessReceipt message="Thanks for reaching out — we'll reply by email soon." />);
    expect(screen.getByText("Thanks for reaching out — we'll reply by email soon.")).toBeInTheDocument();
  });

  it("exposes the confirmation as an announced status region", () => {
    render(<SuccessReceipt message="Done." />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
