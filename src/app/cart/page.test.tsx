import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import CartRoutePage, { metadata } from "./page";

// /cart — signed-in only (GET /cart needs a session), so the route sits
// behind the real ProtectedRoute: an anonymous visitor is redirected to
// /login?returnTo=%2Fcart, never shown a guest cart.
vi.mock("@/components/auth/ProtectedRoute", () => ({
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => <div data-testid="protected">{children}</div>,
}));
vi.mock("@/components/cart/CartView", () => ({
  CartView: () => <div data-testid="cart-view" />,
}));

describe("CartRoutePage (/cart)", () => {
  it("mounts the cart view inside ProtectedRoute", () => {
    render(<CartRoutePage />);
    expect(screen.getByTestId("protected")).toContainElement(screen.getByTestId("cart-view"));
  });

  it("has a page title", () => {
    expect(metadata.title).toMatch(/cart/i);
  });
});
