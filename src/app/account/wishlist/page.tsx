"use client";

import { WishlistList } from "@/components/wishlist/WishlistList";

// FVS-039 (phase 6D) — the customer's wishlist, GET /api/v1/me/wishlist.
// AccountLayout supplies ProtectedRoute, the account nav and the content
// landmark; this page renders only content.
export default function AccountWishlistPage() {
  return (
    <>
      <h1 className="text-h1 font-bold text-text-primary">Wishlist</h1>
      <p className="mt-2 text-body text-text-secondary">Products you&apos;ve saved, newest first.</p>
      <div className="mt-4">
        <WishlistList />
      </div>
    </>
  );
}
