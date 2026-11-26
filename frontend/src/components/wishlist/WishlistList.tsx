"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { PriceDisplay } from "@/components/catalog/PriceDisplay";
import { ProductTypeBadge } from "@/components/catalog/ProductTypeBadge";
import { Alert } from "@/components/feedback/Alert";
import {
  ACCOUNT_CARD,
  AccountErrorCard,
  AccountListSkeleton,
  AccountSessionCard,
} from "@/components/account/accountUi";
import { EmptyState } from "@/components/feedback/EmptyState";
import { Icon } from "@/components/ui/Icon";
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
//
// Batch 7 (Stitch C5 "My Wishlist", direct; COMPONENT-SPECS §11c): a
// 1 -> 2 -> 3 column grid of wishlist cards: media tile with the always
// visible glass remove button (top right) and the stock-style tag (bottom
// left, here only "No longer available"), then title + price and the
// saved date. Deviations: the list item has no image (WishlistItemDTO has
// none), so the media tile shows the Batch 6 fallback glyph; no Add to
// cart, Quick view, rating, filter/sort, share or "add all" (no such
// contract on this list); ProductCard is not reused because it is one
// link around the whole card and would nest the remove control.
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

  if (query.isPending) return <AccountListSkeleton label="Loading your wishlist…" />;
  if (query.isError) {
    if (query.error.kind === "http" && query.error.status === 401) {
      return (
        <AccountSessionCard
          message="Your session has expired. Please sign in again to see your wishlist."
          href={buildLoginRedirectPath("/account/wishlist")}
        />
      );
    }
    return <AccountErrorCard message={WISHLIST_MESSAGES.loadFailed} onRetry={() => void query.refetch()} />;
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
    <div className="flex flex-col gap-6">
      <div ref={noticeRef} tabIndex={-1} className="outline-none empty:hidden">
        {notice?.kind === "ok" && (
          <p
            role="status"
            className="flex items-start gap-3 rounded-card border border-primary/20 bg-secondary-container/40 p-4 text-body-md text-on-surface"
          >
            <Icon name="check-circle" className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
            <span className="min-w-0 break-words">{notice.text}</span>
          </p>
        )}
        {notice?.kind === "error" && <Alert variant="error" message={notice.text} />}
      </div>

      {items.length === 0 ? (
        <div className={ACCOUNT_CARD}>
          <EmptyState
            icon="favorite"
            message="Your wishlist is empty. Tap the heart on a product to save it here."
            actionLabel="Browse the shop"
            actionHref="/shop"
          />
        </div>
      ) : (
        <>
          <p className="border-y border-outline-variant/60 py-4 font-label text-label-caps uppercase text-on-surface">
            Showing {items.length} {items.length === 1 ? "item" : "items"}
          </p>
          <ul className="grid grid-cols-1 gap-gutter tablet:grid-cols-2 xl:grid-cols-3">
            {items.map((item) => (
              <WishlistCard
                key={item.product_id}
                item={item}
                removing={removing === item.product_id}
                disabled={removing !== null}
                onRemove={() => void remove(item)}
              />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function WishlistCard({
  item,
  removing,
  disabled,
  onRemove,
}: {
  item: WishlistItemDTO;
  removing: boolean;
  disabled: boolean;
  onRemove: () => void;
}) {
  const name = item.name || "this product";
  return (
    <li
      className={`group flex flex-col overflow-hidden rounded-card border border-outline-variant/30 bg-surface-container-lowest shadow-sm transition-[box-shadow,transform] duration-300 ease-standard motion-reduce:transition-none ${
        item.available ? "hover:-translate-y-1 hover:shadow-xl motion-reduce:hover:translate-y-0" : ""
      }`}
    >
      <div className="relative aspect-[4/3] w-full bg-surface-container-low">
        <div
          aria-hidden="true"
          className={`flex h-full w-full items-center justify-center text-on-surface-variant ${item.available ? "" : "opacity-50"}`}
        >
          <Icon name={item.type === "stl" ? "deployed-code" : "image"} className="h-12 w-12" strokeWidth={1.25} />
        </div>
        <button
          type="button"
          aria-label={`Remove ${name} from your wishlist`}
          aria-busy={removing || undefined}
          disabled={disabled}
          onClick={onRemove}
          className="absolute right-3 top-3 inline-flex h-11 w-11 items-center justify-center rounded-full border border-outline-variant/30 bg-surface-container-lowest/80 text-error shadow-sm backdrop-blur-sm transition-colors duration-200 ease-standard enabled:hover:bg-error enabled:hover:text-on-error disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none"
        >
          {removing ? (
            <span
              aria-hidden="true"
              className="h-4 w-4 animate-spin rounded-full border-2 border-error/30 border-t-error motion-reduce:animate-none"
            />
          ) : (
            <Icon name="delete" className="h-5 w-5" />
          )}
        </button>
        {!item.available && (
          <span className="absolute bottom-3 left-3 rounded-badge bg-warning-container px-2 py-1 font-label text-label-micro uppercase text-on-warning-container">
            No longer available
          </span>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-3 p-6">
        {item.type && (
          <div>
            <ProductTypeBadge type={item.type} />
          </div>
        )}
        <div className="flex flex-col gap-1">
          <h2 className="min-w-0 break-words font-headline text-headline-md text-on-surface">
            {item.available && item.slug ? (
              <Link href={`/shop/${encodeURIComponent(item.slug)}`} className="hover:text-primary hover:underline">
                {item.name}
              </Link>
            ) : (
              <span>{item.name || "Product no longer available"}</span>
            )}
          </h2>
          {item.price_cents != null && item.currency && (
            <span className="font-headline text-headline-md text-primary">
              <PriceDisplay amountCents={item.price_cents} currency={item.currency} />
            </span>
          )}
        </div>
        <p className="mt-auto font-label text-label-caps uppercase text-on-surface-variant">
          Saved {formatOrderDate(item.created_at)}
        </p>
      </div>
    </li>
  );
}
