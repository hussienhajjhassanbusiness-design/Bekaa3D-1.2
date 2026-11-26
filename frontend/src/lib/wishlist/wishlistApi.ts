import { apiClient } from "@/lib/api/apiClient";
import { authenticatedRequest } from "@/lib/auth/authenticatedRequest";
import type { ProductType } from "@/lib/catalog/productTypes";

// #ARCHITECTURE-WISHLIST-API (phase 6D) — backend 2dfb27b
// engagement/api/wishlist.py (VS-038):
//   GET    /api/v1/me/wishlist?cursor&limit(1-100, default 20)
//          -> {items: WishlistItemRead[], next_cursor}; newest first, the
//          caller's own active items. Session only.
//   PUT    /api/v1/me/wishlist/{product_id}  -> 204, idempotent; 404 for an
//          unknown or non-public product.
//   DELETE /api/v1/me/wishlist/{product_id}  -> 204, idempotent (no 404).
// Both writes need a verified email (403 EMAIL_VERIFICATION_REQUIRED), the
// X-CSRF-Token header and share a 120/h per-user budget (429). There is no
// per-product "is it saved?" route: membership comes from the list.

export interface WishlistItemDTO {
  product_id: string;
  created_at: string;
  // False once the product is soft-deleted or hidden: the row stays, reduced
  // to `name` (slug, type and price are then null).
  available: boolean;
  name: string;
  slug?: string | null;
  type?: ProductType | null;
  price_cents?: number | null;
  currency?: string | null;
}

export interface WishlistPageDTO {
  items: WishlistItemDTO[];
  next_cursor: string | null;
}

export const WISHLIST_PAGE_SIZE = 100;
// A hard stop on cursor-following, so a misbehaving cursor can never loop.
export const WISHLIST_MAX_PAGES = 20;

function itemPath(productId: string): string {
  return `/api/v1/me/wishlist/${encodeURIComponent(productId)}`;
}

function listPage(cursor?: string): Promise<WishlistPageDTO> {
  const search = new URLSearchParams({ limit: String(WISHLIST_PAGE_SIZE) });
  if (cursor) search.set("cursor", cursor);
  return authenticatedRequest(() => apiClient.get<WishlistPageDTO>(`/api/v1/me/wishlist?${search.toString()}`));
}

// The whole wishlist, following `next_cursor` page by page (100 per page).
// One list read serves every heart on a page and the account wishlist, so
// no per-product request is ever made.
async function listAll(): Promise<WishlistItemDTO[]> {
  const items: WishlistItemDTO[] = [];
  let cursor: string | undefined;
  for (let page = 0; page < WISHLIST_MAX_PAGES; page++) {
    const result = await listPage(cursor);
    items.push(...result.items);
    if (!result.next_cursor) break;
    cursor = result.next_cursor;
  }
  return items;
}

function add(productId: string): Promise<void> {
  return authenticatedRequest(() => apiClient.put<void>(itemPath(productId), undefined, { csrf: true }));
}

function remove(productId: string): Promise<void> {
  return authenticatedRequest(() => apiClient.del<void>(itemPath(productId), { csrf: true }));
}

export const wishlistApi = { listPage, listAll, add, remove };

// #ARCHITECTURE-CANONICAL-WISHLIST-QUERY — the ONE wishlist cache. Product
// cards, the product page and /account/wishlist all read `all`; every write
// updates or re-reads it. Under the user-scoped ["wishlist"] root
// (userScopedQueries.ts): dropped on logout, cross-tab logout and user switch.
export const wishlistKeys = {
  root: ["wishlist"] as const,
  all: () => [...wishlistKeys.root, "all"] as const,
};
