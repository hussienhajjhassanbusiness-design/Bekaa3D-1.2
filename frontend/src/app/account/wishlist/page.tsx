"use client";

import { WishlistList } from "@/components/wishlist/WishlistList";
import { PageHeader } from "@/components/ui/PageHeader";

// FVS-039 (phase 6D) — the customer's wishlist, GET /api/v1/me/wishlist.
// AccountLayout supplies ProtectedRoute, the account nav and the content
// landmark; this page renders only content.
export default function AccountWishlistPage() {
  return (
    <>
      <PageHeader eyebrow="Account" title="Wishlist" description="Products you've saved, newest first." />
      <WishlistList />
    </>
  );
}
