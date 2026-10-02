// #SHARED-ACCOUNT-NAVIGATION
//
// The single registry every /account/* page's nav link comes from.
// Future account slices (Orders, Downloads, Offers, Wishlist, Reviews,
// Addresses, Notifications) add themselves here as their own routes land
// — never as a disabled/dead placeholder ahead of time. AccountLayout
// renders exactly this list; it has no second, hand-maintained copy.
export interface AccountNavItem {
  label: string;
  href: string;
}

export const ACCOUNT_NAV_ITEMS: readonly AccountNavItem[] = [{ label: "Profile", href: "/account/profile" }];
