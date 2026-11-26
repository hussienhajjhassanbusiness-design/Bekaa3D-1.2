"use client";

import Link from "next/link";
import { useState } from "react";
import { Alert } from "@/components/feedback/Alert";
import { Button, buttonLinkClassName } from "@/components/forms/Button";
import { Icon } from "@/components/ui/Icon";
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
      <a href={buildLoginRedirectPath(returnToPath)} className={`${buttonLinkClassName("primary", "lg")} w-full`}>
        <Icon name="shopping-cart" className="h-5 w-5" />
        Add to cart
      </a>
    );
  }

  if (!user.emailVerified) {
    return (
      <p className="font-body text-body-md text-on-surface-variant">
        <Link href="/verify-email/resend" className="font-semibold text-primary underline underline-offset-4">
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

const STEPPER_BUTTON_CLASS =
  "inline-flex h-12 w-12 items-center justify-center text-on-surface-variant transition-colors duration-200 enabled:hover:bg-surface-container enabled:hover:text-primary disabled:cursor-not-allowed disabled:opacity-40";

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
    // Batch 3 — Stitch PDP action row (PAGE-SPECS S4): a square-cornered
    // stepper (COMPONENT-SPECS §26) beside a full-width primary lg "Add to
    // cart". Same buttons, labels, limits and disabled rules as before.
    <div className="flex w-full flex-col gap-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
        {isPhysical && (
          <div className="flex flex-col gap-1">
            <div
              className="inline-flex min-h-13 items-center rounded-control border-2 border-outline-variant bg-surface-container-lowest"
              role="group"
              aria-label={`Quantity of ${productName}`}
            >
              <button
                type="button"
                className={STEPPER_BUTTON_CLASS}
                onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                disabled={addToCart.isPending || quantity <= 1}
                aria-label="Decrease quantity"
              >
                <Icon name="remove" className="h-5 w-5" />
              </button>
              <span aria-live="polite" className="min-w-10 flex-1 text-center font-body text-body-md font-semibold text-on-surface tabular-nums">
                {quantity}
              </span>
              <button
                type="button"
                className={STEPPER_BUTTON_CLASS}
                onClick={() => setQuantity((q) => (cap === null ? q + 1 : Math.min(cap, q + 1)))}
                disabled={addToCart.isPending || (cap !== null && quantity >= cap)}
                aria-label="Increase quantity"
              >
                <Icon name="add" className="h-5 w-5" />
              </button>
            </div>
            {cap !== null && <p className="font-body text-sm text-on-surface-variant">Maximum {cap} per order</p>}
          </div>
        )}
        <Button type="button" size="lg" className="w-full sm:flex-1" onClick={() => void handleAdd()} isLoading={addToCart.isPending}>
          {addToCart.isPending ? null : <Icon name="shopping-cart" className="h-5 w-5" />}
          {addToCart.isPending ? "Adding…" : "Add to cart"}
        </Button>
      </div>

      {result?.ok && (
        <p role="status" className="font-body text-body-md text-on-surface">
          Added to your cart.{" "}
          <Link href="/cart" className="font-semibold text-primary underline underline-offset-4">
            View cart
          </Link>
        </p>
      )}
      {result && !result.ok && <Alert variant="error" message={result.message} />}
    </div>
  );
}
