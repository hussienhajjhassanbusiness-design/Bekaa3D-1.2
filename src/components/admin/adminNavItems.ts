// #SHARED-ADMIN-NAVIGATION
//
// The single registry every /admin/* page's nav link comes from —
// mirrors src/components/account/accountNavItems.ts's pattern. Lists
// only the BUILT, authoritative admin areas (AGENTS.md Phase 3 scope):
// settings, customers, reference data, products, (phase 5H) orders and the
// STL delivery queue, (phase 5I) payments and refunds, and (phase 6A) cash
// blocks, (phase 6B) the contact queue and the Bring Your Idea pipeline, and
// (phase 6C) the offer queue. Deliberately
// excludes STL asset versions / entitlement grants /
// shipping zones (removed by ADR-019/ADR-024): no nav entry for them
// exists, not even disabled.
//
// Redesign Batch 9: the same items, in the same order, grouped under mono
// section labels for the Stitch admin sidebar (COMPONENT-SPECS §40, admin
// console grouped variant), each with a local decorative icon.
import type { IconName } from "@/components/ui/Icon";

export interface AdminNavItem {
  label: string;
  href: string;
  icon: IconName;
}

export interface AdminNavGroup {
  label: string;
  items: readonly AdminNavItem[];
}

export const ADMIN_NAV_GROUPS: readonly AdminNavGroup[] = [
  {
    label: "Fulfilment",
    items: [
      { label: "Orders", href: "/admin/orders", icon: "receipt-long" },
      { label: "STL deliveries", href: "/admin/stl-deliveries", icon: "mail" },
      { label: "Offers", href: "/admin/offers", icon: "sell" },
    ],
  },
  {
    label: "Money",
    items: [
      { label: "Payments", href: "/admin/payments", icon: "payments" },
      { label: "Refunds", href: "/admin/refunds", icon: "undo" },
      { label: "Cash blocks", href: "/admin/cash-blocks", icon: "block" },
    ],
  },
  {
    label: "Enquiries",
    items: [
      { label: "Contact messages", href: "/admin/contact-messages", icon: "notifications" },
      { label: "Bring Your Idea", href: "/admin/custom-requests", icon: "lightbulb" },
    ],
  },
  {
    label: "Store",
    items: [
      { label: "Settings", href: "/admin/settings", icon: "settings" },
      { label: "Customers", href: "/admin/customers", icon: "group" },
    ],
  },
  {
    label: "Catalogue",
    items: [
      { label: "Categories", href: "/admin/categories", icon: "category" },
      { label: "Materials", href: "/admin/materials", icon: "layers" },
      { label: "Colours", href: "/admin/colours", icon: "palette" },
      { label: "Products", href: "/admin/products", icon: "storefront" },
    ],
  },
];

export const ADMIN_NAV_ITEMS: readonly AdminNavItem[] = ADMIN_NAV_GROUPS.flatMap((group) => group.items);

export function isAdminNavItemActive(item: AdminNavItem, pathname: string | null): boolean {
  return pathname === item.href || (pathname?.startsWith(`${item.href}/`) ?? false);
}
