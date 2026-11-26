import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import CheckoutRoutePage, { metadata } from "./page";

// /checkout needs a verified session, so it sits behind the real
// ProtectedRoute (anonymous -> /login?returnTo=%2Fcheckout).
vi.mock("@/components/auth/ProtectedRoute", () => ({
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => <div data-testid="protected">{children}</div>,
}));
vi.mock("@/components/checkout/CheckoutView", () => ({
  CheckoutView: () => <div data-testid="checkout-view" />,
}));

describe("CheckoutRoutePage (/checkout)", () => {
  it("mounts the checkout view inside ProtectedRoute", () => {
    render(<CheckoutRoutePage />);
    expect(screen.getByTestId("protected")).toContainElement(screen.getByTestId("checkout-view"));
  });

  it("has a page title", () => {
    expect(metadata.title).toMatch(/checkout/i);
  });
});
