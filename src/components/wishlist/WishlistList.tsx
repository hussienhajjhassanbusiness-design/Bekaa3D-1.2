"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { ProductTypeBadge } from "@/components/catalog/ProductTypeBadge";
import { Alert } from "@/components/feedback/Alert";
import { LoadingSpinner } from "@/components/feedback/LoadingSpinner";
import { Button } from "@/components/forms/Button";
import { AUTH_SESSION_QUERY_KEY } from "@/lib/auth/authSession";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";
import { formatOrderDate } from "@/lib/orders/orderFormat";
import type { WishlistItemDTO } from "@/lib/wishlist/wishlistApi";
import { describeWishlistError, useToggleWishlist, useWishlist, WISHLIST_MESSAGES } from "@/lib/wishlist/useWishlist";

// #FVS-WISHLIST-ACCOUNT (phase 6D) — /account/wishlist, from the one
// canonical wishlist query (GET /api/v1/me/wishlist, every page followed).
// A product that has since been hidden or deleted stays listed by name with
// "No longer available" and only a Remove action, exactly as the server
// returns it (`available: false`, name only).
export function WishlistList() {
  const query = useWishlist();
  const queryClient = useQueryClient();
  const toggle = useToggleWishlist();
  const inFlight = useRef(false);
  // The removed row (and its button) leaves the page, so focus moves to the
  // result instead of falling back to <body>.
  const noticeRef = useRef<HTMLDivElement>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  if (query.isPending) return <LoadingSpinner />;
  if (query.isError) {
    if (query.error.kind === "http" && query.error.status === 401) {
      return (
        <div role="alert" className="flex flex-col items-start gap-3 rounded-md border-l-4 border-l-warning bg-warning-bg p-4">
          <p className="text-body text-text-primary">Your session has expired. Please sign in again to see your wishlist.</p>
          <Link href={buildLoginRedirectPath("/account/wishlist")} className="font-semibold text-brand-dark-green underline">
            Sign in
          </Link>
        </div>
      );
    }
    return (
      <div role="alert" className="flex flex-col items-start gap-3 rounded-md border-l-4 border-l-danger bg-danger-bg p-4">
        <p className="text-body text-text-primary">{WISHLIST_MESSAGES.loadFailed}</p>
        <Button type="button" variant="secondary" onClick={() => void query.refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  async function remove(item: WishlistItemDTO) {
    if (inFlight.current) return;
    inFlight.current = true;
    setRemoving(item.product_id);
    setNotice(null);
    try {
      await toggle.mutateAsync({ productId: item.product_id, save: false });
      setNotice({ kind: "ok", text: `Removed ${item.name || "the product"} from your wishlist.` });
    } catch (error) {
      const outcome = describeWishlistError(error);
      if (outcome.refetchAuth) void queryClient.invalidateQueries({ queryKey: AUTH_SESSION_QUERY_KEY });
      setNotice({ kind: "error", text: outcome.message });
    } finally {
      inFlight.current = false;
      setRemoving(null);
      requestAnimationFrame(() => noticeRef.current?.focus());
    }
  }

  const items = query.data;
  return (
    <div className="flex flex-col gap-4">
      <div ref={noticeRef} tabIndex={-1} className="outline-none">
        {notice?.kind === "ok" && (
          <p role="status" className="rounded-md border-l-4 border-l-success bg-success-bg p-3 text-body text-text-primary">
            {notice.text}
          </p>
        )}
        {notice?.kind === "error" && <Alert variant="error" message={notice.text} />}
      </div>

      {items.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-12 text-center">
          <p className="text-body text-text-secondary">Your wishlist is empty. Tap the heart on a product to save it here.</p>
          <Link href="/shop" className="font-semibold text-brand-dark-green underline">
            Browse the shop
          </Link>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((item) => (
            <li key={item.product_id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border-default bg-white p-4">
              <div className="flex min-w-0 flex-col gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  {item.type && <ProductTypeBadge type={item.type} />}
                  {!item.available && (
                    <span className="rounded-pill bg-warning-bg px-2 py-0.5 text-caption font-semibold text-warning">No longer available</span>
                  )}
                </div>
                {item.available && item.slug ? (
                  <Link href={`/shop/${encodeURIComponent(item.slug)}`} className="break-words text-body font-semibold text-brand-dark-green underline">
                    {item.name}
                  </Link>
                ) : (
                  <span className="break-words text-body font-semibold text-text-primary">{item.name || "Product no longer available"}</span>
                )}
                <p className="text-caption text-text-secondary">Saved {formatOrderDate(item.created_at)}</p>
              </div>
              <div className="flex items-center gap-3">
                {item.price_cents != null && item.currency && (
                  <span className="font-semibold text-text-primary">
                    <PriceDisplay amountCents={item.price_cents} currency={item.currency} />
                  </span>
                )}
                <Button
                  type="button"
                  variant="secondary"
                  isLoading={removing === item.product_id}
                  disabled={removing !== null}
                  aria-label={`Remove ${item.name || "this product"} from your wishlist`}
                  onClick={() => void remove(item)}
                >
                  Remove
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
