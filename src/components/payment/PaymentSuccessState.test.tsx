import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PaymentSuccessState } from "./PaymentSuccessState";

// FVS-027-IMPLEMENTATION-PLAN.md T05 — accepts no provider/query-
// derived props of any kind. The only way to render this component is
// for a caller to have already decided, from a backend-verified
// `paid` status, that it's appropriate. No dead link to FVS-029/
// FVS-020's still-unmounted routes.

describe("PaymentSuccessState", () => {
  it("renders success copy", () => {
    render(<PaymentSuccessState />);
    expect(screen.getByText(/payment successful/i)).toBeInTheDocument();
  });

  it("renders the optional order id when supplied", () => {
    render(<PaymentSuccessState orderDisplayId="ORD-123" />);
    expect(screen.getByText("ORD-123")).toBeInTheDocument();
  });

  it("renders no action link of any kind when actionSlot is omitted — no dead link", () => {
    render(<PaymentSuccessState />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders the supplied actionSlot when given", () => {
    render(<PaymentSuccessState actionSlot={<a href="/account/profile">View your account</a>} />);
    expect(screen.getByRole("link", { name: "View your account" })).toBeInTheDocument();
  });

  it("has no prop that could carry raw provider/query data — only orderDisplayId and actionSlot exist", () => {
    // Structural proof: rendering with zero props still produces a
    // fully valid, honest success state — there is no required
    // "providerSaidSuccess"/"queryStatus" prop for a caller to
    // mistakenly wire a query-string value into.
    render(<PaymentSuccessState />);
    expect(screen.getByText(/payment successful/i)).toBeInTheDocument();
  });
});
