// #SHARED-ADMIN-NAVIGATION
//
// The single registry every /admin/* page's nav link comes from —
// mirrors src/components/account/accountNavItems.ts's pattern. Lists
// only the BUILT, authoritative admin areas (AGENTS.md Phase 3 scope):
// settings, customers, reference data, products, (phase 5H) orders and the
// STL delivery queue, (phase 5I) payments and refunds, and (phase 6A) cash
// blocks, and (phase 6B) the contact queue and the Bring Your Idea pipeline. Deliberately
// excludes STL asset versions / entitlement grants /
// shipping zones (removed by ADR-019/ADR-024): no nav entry for them
// exists, not even disabled.
export interface AdminNavItem {
  label: string;
  href: string;
}

export const ADMIN_NAV_ITEMS: readonly AdminNavItem[] = [
  { label: "Orders", href: "/admin/orders" },
  { label: "STL deliveries", href: "/admin/stl-deliveries" },
  { label: "Payments", href: "/admin/payments" },
  { label: "Refunds", href: "/admin/refunds" },
  { label: "Cash blocks", href: "/admin/cash-blocks" },
  { label: "Contact messages", href: "/admin/contact-messages" },
  { label: "Bring Your Idea", href: "/admin/custom-requests" },
  { label: "Settings", href: "/admin/settings" },
  { label: "Customers", href: "/admin/customers" },
  { label: "Categories", href: "/admin/categories" },
  { label: "Materials", href: "/admin/materials" },
  { label: "Colours", href: "/admin/colours" },
  { label: "Products", href: "/admin/products" },
];
