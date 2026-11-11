// #SHARED-ACCOUNT-NAVIGATION
//
// The single registry every /account/* page's nav link comes from.
// Future account slices (Orders, Offers, Wishlist, Reviews, Addresses)
// add themselves here as their own routes land — never as a
// disabled/dead placeholder ahead of time. There is no "Downloads" or
// "Library" slice: ADR-019 removed STL entitlements/downloads
// permanently. AccountLayout renders exactly this list; it has no
// second, hand-maintained copy.
export interface AccountNavItem {
  label: string;
  href: string;
}

export const ACCOUNT_NAV_ITEMS: readonly AccountNavItem[] = [
  { label: "Profile", href: "/account/profile" },
  { label: "Orders", href: "/account/orders" },
  { label: "Offers", href: "/account/offers" },
  { label: "Addresses", href: "/account/addresses" },
  { label: "Notifications", href: "/account/notifications" },
];
