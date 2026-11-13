// #SHARED-ACCOUNT-NAVIGATION
//
// The single registry every /account/* page's nav link comes from.
// Future account slices (Orders, Offers, Wishlist, Reviews, Addresses)
// add themselves here as their own routes land — never as a
// disabled/dead placeholder ahead of time. There is no "Downloads" or
// "Library" slice: ADR-019 removed STL entitlements/downloads
// permanently. AccountLayout renders exactly this list; it has no
// second, hand-maintained copy.
import type { IconName } from "@/components/ui/Icon";

export interface AccountNavItem {
  label: string;
  href: string;
  // Decorative glyph (Batch 5); the label is always the accessible name.
  icon: IconName;
}

export const ACCOUNT_NAV_ITEMS: readonly AccountNavItem[] = [
  { label: "Profile", href: "/account/profile", icon: "person" },
  { label: "Orders", href: "/account/orders", icon: "shopping-bag" },
  { label: "Offers", href: "/account/offers", icon: "sell" },
  { label: "Wishlist", href: "/account/wishlist", icon: "favorite" },
  { label: "Addresses", href: "/account/addresses", icon: "location-on" },
  { label: "Notifications", href: "/account/notifications", icon: "notifications" },
];
