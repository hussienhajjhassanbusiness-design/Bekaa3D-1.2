import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AddToCartButton } from "./AddToCartButton";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";

// FVS-014-IMPLEMENTATION-PLAN.md §0 — cart-dependency discrepancy
// resolution: the source says BOTH "ships disabled/hidden if cart
// doesn't exist yet" AND "for an anonymous visitor the button is always
// enabled and redirects to /login". Read as two different viewer
// states rather than a flat contradiction: the anonymous→login-redirect
// path is a pure auth-gate that needs no cart at all (so it is safe to
// build now, reusing FVS-003's existing buildLoginRedirectPath rather
// than duplicating redirect-safety logic); the authenticated
// "actually add to cart" path genuinely needs FVS-025 and stays hidden
// until then. No guest cart, no fake cart state, no placeholder POST.

describe("AddToCartButton", () => {
  it("renders an enabled login-redirect link for an anonymous visitor", () => {
    render(<AddToCartButton isAuthenticated={false} returnToPath="/shop/my-product" />);
    expect(screen.getByRole("link", { name: /add to cart/i })).toBeInTheDocument();
  });

  it("builds the redirect href using the existing safe returnTo helper, not a duplicate", () => {
    render(<AddToCartButton isAuthenticated={false} returnToPath="/shop/my-product" />);
    const href = screen.getByRole("link").getAttribute("href");
    expect(href).toBe(buildLoginRedirectPath("/shop/my-product"));
  });

  it("renders nothing for an authenticated visitor (hidden until FVS-025)", () => {
    render(<AddToCartButton isAuthenticated={true} returnToPath="/shop/my-product" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("never makes a network/fetch call", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<AddToCartButton isAuthenticated={false} returnToPath="/shop/my-product" />);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("never writes to localStorage or sessionStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    render(<AddToCartButton isAuthenticated={false} returnToPath="/shop/my-product" />);
    expect(spy).not.toHaveBeenCalled();
  });
});
