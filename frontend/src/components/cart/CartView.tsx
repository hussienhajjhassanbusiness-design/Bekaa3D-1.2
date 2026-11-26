"use client";

import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AUTH_SESSION_QUERY_KEY } from "@/lib/auth/authSession";
import { useAuth } from "@/lib/auth/AuthProvider";
import { CART_MESSAGES, describeCartWriteError } from "@/lib/cart/cartErrors";
import { useCart, useRemoveCartItem, useSetCartItemQuantity } from "@/lib/cart/useCart";
import { Container } from "@/components/ui/Container";
import { CartPage } from "./CartPage";

function withoutKey(record: Readonly<Record<string, string>>, key: string): Readonly<Record<string, string>> {
  const next = { ...record };
  delete next[key];
  return next;
}

// #FVS025-CART-VIEW
//
// The /cart container: the canonical cart query plus the PATCH/DELETE
// mutations. Each line tracks its own in-flight write, so a line's
// controls stay disabled until the server answers (no optimistic quantity,
// and no two writes for one line racing each other). Failed writes show
// frontend-owned copy on that line; the hooks refetch when the failure
// means the cart shown is stale. After a successful remove, focus moves
// to the page heading because the focused control no longer exists.
export function CartView() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const cartQuery = useCart();
  const setQuantity = useSetCartItemQuantity();
  const removeItem = useRemoveCartItem();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());
  const [lineErrors, setLineErrors] = useState<Readonly<Record<string, string>>>({});

  async function runLineWrite(productId: string, write: () => Promise<unknown>): Promise<boolean> {
    setPending((current) => new Set(current).add(productId));
    setLineErrors((current) => withoutKey(current, productId));
    try {
      await write();
      return true;
    } catch (error) {
      setLineErrors((current) => ({
        ...current,
        [productId]: describeCartWriteError(error).message,
      }));
      return false;
    } finally {
      setPending((current) => {
        const next = new Set(current);
        next.delete(productId);
        return next;
      });
    }
  }

  function handleQuantityChange(productId: string, quantity: number) {
    void runLineWrite(productId, () => setQuantity.mutateAsync({ productId, quantity }));
  }

  async function handleRemove(productId: string) {
    const removed = await runLineWrite(productId, () => removeItem.mutateAsync({ productId }));
    if (removed) {
      headingRef.current?.focus();
    }
  }

  // ProtectedRoute lets children through on a genuine auth-query error;
  // without a user the cart query never runs, so say so rather than
  // showing an empty cart.
  const authFailed = auth.isError && !auth.user;

  return (
    <Container className="flex flex-col gap-8 py-10 tablet:py-12 desktop:gap-12 desktop:py-16">
      {/* Stitch S6 page header: display-role h1 + one-line description. */}
      <div className="flex max-w-2xl flex-col gap-3">
        <h1
          ref={headingRef}
          tabIndex={-1}
          className="break-words font-display text-display text-on-surface outline-none"
        >
          Your cart
        </h1>
        <p className="text-body-md text-on-surface-variant">
          Review your physical items and STL files before you check out.
        </p>
      </div>
      <CartPage
        cart={cartQuery.data ?? null}
        isLoading={!authFailed && cartQuery.isPending && cartQuery.fetchStatus !== "idle"}
        isError={authFailed || cartQuery.isError}
        onRetry={() =>
          authFailed
            ? void queryClient.invalidateQueries({
                queryKey: AUTH_SESSION_QUERY_KEY,
              })
            : void cartQuery.refetch()
        }
        onQuantityChange={handleQuantityChange}
        onRemove={(productId) => void handleRemove(productId)}
        pendingProductIds={pending}
        lineErrors={lineErrors}
        notice={auth.user && !auth.user.emailVerified ? CART_MESSAGES.verifyEmail : undefined}
        canCheckout={Boolean(auth.user?.emailVerified)}
      />
    </Container>
  );
}
