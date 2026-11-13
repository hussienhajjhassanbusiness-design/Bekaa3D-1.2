"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/ui/Icon";
import { cartItemCount } from "@/lib/cart/cartModel";
import { useCart } from "@/lib/cart/useCart";

// #FVS025-HEADER-CART-LINK
//
// A link to /cart for everyone (an anonymous visitor is sent to log in by
// /cart's ProtectedRoute). For a signed-in user, the unit count is derived
// from the ONE canonical cart query (useCart, enabled only when signed
// in), the same cache /cart and Add to cart use. There is no cart-count
// endpoint, and this does not add a second cart cache.
//
// Stitch header icon button + cart badge (COMPONENT-SPECS §4): 40px hit
// area, 24px glyph, round hover tint, 16px primary count badge. The count
// is visual only; the accessible name carries it.
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
      className={`relative inline-flex h-10 w-10 items-center justify-center rounded-full transition-colors duration-200 hover:bg-surface-container hover:text-primary ${
        isActive ? "text-primary" : "text-on-surface-variant"
      }`}
    >
      <Icon name="shopping-cart" />
      {count > 0 && (
        <span
          aria-hidden="true"
          className="absolute right-0 top-0 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 font-body text-label-micro font-bold leading-none text-on-primary tabular-nums"
        >
          {count > 99 ? "99+" : count}
        </span>
      )}
    </Link>
  );
}
