"use client";

import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { EmptyState } from "@/components/feedback/EmptyState";
import { CartLineItem } from "./CartLineItem";
import type { CartModel } from "@/lib/cart/cartModel";

export interface CartPageProps {
  cart: CartModel | null;
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
  onQuantityChange: (lineId: string, nextQuantity: number) => void;
  onRemove: (lineId: string) => void;
  unavailableNoticeByLineId?: Readonly<Record<string, string>>;
}

const EMPTY_MESSAGE = "Your cart is empty.";
const DEFAULT_ERROR_MESSAGE = "We couldn't load your cart. Please try again.";

// #FVS025-CART-PAGE
//
// Presentational only — no network, no query, not mounted to a route
// this batch (T09 blocked, FVS-025-IMPLEMENTATION-PLAN.md §6). No
// summary/totals area is built — no source confirms GET /cart returns
// one (#ARCHITECTURE-CART-ADAPTER). No Checkout link/button anywhere:
// /checkout doesn't exist yet, matching the dead-link rule already
// applied in FVS-022.
export function CartPage({
  cart,
  isLoading = false,
  isError = false,
  errorMessage,
  onRetry,
  onQuantityChange,
  onRemove,
  unavailableNoticeByLineId,
}: CartPageProps) {
  if (isLoading) {
    return (
      <div role="status">
        <span className="sr-only">Loading your cart…</span>
        {[0, 1].map((index) => (
          <div
            key={index}
            aria-hidden="true"
            className="mt-2 h-20 animate-pulse rounded bg-neutral-200 motion-reduce:animate-none"
          />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        <Alert variant="error" message={errorMessage ?? DEFAULT_ERROR_MESSAGE} />
        {onRetry && (
          <Button onClick={onRetry} className="mt-2">
            Retry
          </Button>
        )}
      </div>
    );
  }

  if (!cart || cart.lines.length === 0) {
    return <EmptyState message={EMPTY_MESSAGE} />;
  }

  return (
    <ul className="flex flex-col gap-4">
      {cart.lines.map((line) => (
        <li key={line.id}>
          <CartLineItem
            line={line}
            onQuantityChange={onQuantityChange}
            onRemove={onRemove}
            unavailableNotice={unavailableNoticeByLineId?.[line.id]}
          />
        </li>
      ))}
    </ul>
  );
}
