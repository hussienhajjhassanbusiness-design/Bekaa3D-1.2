"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cartItemCount } from "@/lib/cart/cartModel";
import { useCart } from "@/lib/cart/useCart";

// #FVS025-HEADER-CART-LINK
//
// A link to /cart for everyone (an anonymous visitor is sent to log in by
// /cart's ProtectedRoute). For a signed-in user, the unit count is derived
// from the ONE canonical cart query (useCart, enabled only when signed
// in), the same cache /cart and Add to cart use. There is no cart-count
// endpoint, and this does not add a second cart cache.
export function HeaderCartLink() {
  const pathname = usePathname();
  const cartQuery = useCart();
  const count = cartQuery.data ? cartItemCount(cartQuery.data) : 0;
  const isActive = pathname === "/cart";

  return (
    <Link
      href="/cart"
      aria-current={isActive ? "page" : undefined}
      aria-label={count > 0 ? `Cart, ${count} item${count === 1 ? "" : "s"}` : "Cart"}
      className={`flex h-10 items-center gap-2 rounded-md px-2 text-body ${
        isActive ? "font-semibold text-brand-dark-green" : "text-text-primary hover:text-brand-dark-green"
      }`}
    >
      <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 4h2l2.4 10.2a1 1 0 0 0 1 .8h8.9a1 1 0 0 0 1-.8L20 8H6.2" />
        <circle cx="9" cy="19" r="1.4" />
        <circle cx="17" cy="19" r="1.4" />
      </svg>
      <span aria-hidden="true">Cart</span>
      {count > 0 && (
        <span
          aria-hidden="true"
          className="min-w-6 rounded-pill bg-brand-dark-green px-2 text-center text-caption font-semibold text-text-on-brand"
        >
          {count}
        </span>
      )}
    </Link>
  );
}
