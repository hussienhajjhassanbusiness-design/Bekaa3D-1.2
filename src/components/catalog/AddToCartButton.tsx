"use client";

import Link from "next/link";
import { useState } from "react";
import { Alert } from "@/components/feedback/Alert";
import { Button } from "@/components/forms/Button";
import { useAuth } from "@/lib/auth/AuthProvider";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";
import { describeCartWriteError } from "@/lib/cart/cartErrors";
import { useAddToCart } from "@/lib/cart/useCart";
import type { ProductType } from "@/lib/catalog/productTypes";

export interface AddToCartButtonProps {
  productId: string;
  productType: ProductType;
  productName: string;
  // ProductDetail.capabilities.can_add_to_cart — the backend's own
  // product-level answer (unavailable, WhatsApp-only, unlisted all false).
  // Never inferred from the product type.
  canAddToCart: boolean;
  // ProductDetail.max_quantity_per_line (null for STL).
  maxQuantityPerLine: number | null;
  returnToPath: string;
}

// #FVS014-ADD-TO-CART / #FVS025-ADD-TO-CART
//
// POST /api/v1/cart/items `{product_id, quantity}` (CSRF; verified email).
// - capability false: renders nothing, so no request can be sent.
// - anonymous: a login-redirect link (the shared safe returnTo helper);
//   there is no guest cart.
// - signed in, unverified: the backend would answer 403
//   EMAIL_VERIFICATION_REQUIRED, so point to verification instead.
// - verified: STL always adds quantity 1 with no control; physical gets a
//   stepper bounded by max_quantity_per_line. Adding merges into an
//   existing line server-side, and the server still enforces the cap on
//   the merged quantity (422 QUANTITY_EXCEEDS_LIMIT -> safe copy).
// No optimistic state: the canonical cart query is updated from the
// server's CartRead response (useAddToCart).
export function AddToCartButton({
  productId,
  productType,
  productName,
  canAddToCart,
  maxQuantityPerLine,
  returnToPath,
}: AddToCartButtonProps) {
  const { user, isLoading } = useAuth();

  if (!canAddToCart || isLoading) {
    return null;
  }

  if (!user) {
    return (
      <a
        href={buildLoginRedirectPath(returnToPath)}
        className="inline-block rounded-md bg-brand-dark-green px-4 py-2 text-text-on-brand"
      >
        Add to cart
      </a>
    );
  }

  if (!user.emailVerified) {
    return (
      <p className="text-body text-text-secondary">
        <Link href="/verify-email/resend" className="text-brand-dark-green underline">
          Verify your email
        </Link>{" "}
        to add products to your cart.
      </p>
    );
  }

  return (
    <VerifiedAddToCart
      productId={productId}
      productType={productType}
      productName={productName}
      maxQuantityPerLine={maxQuantityPerLine}
    />
  );
}

function VerifiedAddToCart({
  productId,
  productType,
  productName,
  maxQuantityPerLine,
}: Pick<AddToCartButtonProps, "productId" | "productType" | "productName" | "maxQuantityPerLine">) {
  const addToCart = useAddToCart();
  const [quantity, setQuantity] = useState(1);
  const [result, setResult] = useState<{ ok: true } | { ok: false; message: string } | null>(null);
  const isPhysical = productType === "physical";
  const cap = isPhysical ? maxQuantityPerLine : 1;

  async function handleAdd() {
    setResult(null);
    try {
      await addToCart.mutateAsync({ productId, quantity: isPhysical ? quantity : 1 });
      setResult({ ok: true });
    } catch (error) {
      setResult({ ok: false, message: describeCartWriteError(error).message });
    }
  }

  return (
    <div className="flex w-full flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        {isPhysical && (
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2" role="group" aria-label={`Quantity of ${productName}`}>
              <Button
                type="button"
                variant="secondary"
                className="h-10 w-10 px-0 py-0"
                onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                disabled={addToCart.isPending || quantity <= 1}
                aria-label="Decrease quantity"
              >
                −
              </Button>
              <span aria-live="polite" className="min-w-8 text-center text-body font-semibold text-text-primary">
                {quantity}
              </span>
              <Button
                type="button"
                variant="secondary"
                className="h-10 w-10 px-0 py-0"
                onClick={() => setQuantity((q) => (cap === null ? q + 1 : Math.min(cap, q + 1)))}
                disabled={addToCart.isPending || (cap !== null && quantity >= cap)}
                aria-label="Increase quantity"
              >
                +
              </Button>
            </div>
            {cap !== null && <p className="text-caption text-text-secondary">Maximum {cap} per order</p>}
          </div>
        )}
        <Button type="button" onClick={() => void handleAdd()} isLoading={addToCart.isPending}>
          {addToCart.isPending ? "Adding…" : "Add to cart"}
        </Button>
      </div>

      {result?.ok && (
        <p role="status" className="text-body text-text-primary">
          Added to your cart.{" "}
          <Link href="/cart" className="font-semibold text-brand-dark-green underline">
            View cart
          </Link>
        </p>
      )}
      {result && !result.ok && <Alert variant="error" message={result.message} />}
    </div>
  );
}
