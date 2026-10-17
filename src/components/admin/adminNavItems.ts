// #SHARED-ADMIN-NAVIGATION
//
// The single registry every /admin/* page's nav link comes from —
// mirrors src/components/account/accountNavItems.ts's pattern. Lists
// only the BUILT, authoritative admin areas (AGENTS.md Phase 3 scope):
// settings, customers, reference data, products. Deliberately excludes
// admin payments/orders/refunds/cancellation/contact-queue/STL-asset-
// versions/entitlement-grants/shipping-zones — those backend routes
// are not built (or are removed by ADR-019/ADR-024), so no nav entry
// for them exists, not even disabled.
export interface AdminNavItem {
  label: string;
  href: string;
}

export const ADMIN_NAV_ITEMS: readonly AdminNavItem[] = [
  { label: "Settings", href: "/admin/settings" },
  { label: "Customers", href: "/admin/customers" },
  { label: "Categories", href: "/admin/categories" },
  { label: "Materials", href: "/admin/materials" },
  { label: "Colours", href: "/admin/colours" },
  { label: "Products", href: "/admin/products" },
];
