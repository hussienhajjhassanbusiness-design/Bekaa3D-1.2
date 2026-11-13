"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth/AuthProvider";
import { AUTH_SESSION_QUERY_KEY } from "@/lib/auth/authSession";
import { buildLoginRedirectPath } from "@/lib/auth/returnTo";
import { describeWishlistError, useToggleWishlist, useWishlist } from "@/lib/wishlist/useWishlist";

export interface WishlistButtonProps {
  productId: string;
  productName: string;
  returnToPath: string;
  // "icon": the heart overlaid on a product card; "full": a labelled button
  // on the product page.
  variant: "icon" | "full";
}

function Heart({ filled }: { filled: boolean }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
      <path
        strokeLinejoin="round"
        d="M12 20.5s-7.5-4.6-9.2-9.3C1.7 8 3.6 4.5 7.1 4.5c2 0 3.6 1.1 4.9 2.9 1.3-1.8 2.9-2.9 4.9-2.9 3.5 0 5.4 3.5 4.3 6.7-1.7 4.7-9.2 9.3-9.2 9.3z"
      />
    </svg>
  );
}

// Icon: the Stitch card heart (COMPONENT-SPECS §11a/§11c) — a translucent
// white circle over the image corner, always visible (never hover-only, so
// touch and keyboard users get it too); saved = filled heart in the Stitch
// favourite colour. Kept at 44px (Stitch: 40px) for the touch-target size.
const ICON_CLASS =
  "inline-flex h-11 w-11 items-center justify-center rounded-full bg-surface-container-lowest/90 text-on-surface-variant shadow-sm backdrop-blur-sm transition-colors duration-200 hover:text-error aria-pressed:text-error";
// Full: the product page's neutral outline action (Stitch secondary row).
const FULL_CLASS =
  "inline-flex min-h-13 w-full items-center justify-center gap-2 rounded-control border-2 border-outline-variant bg-surface-container-lowest px-6 py-3 font-label text-label-caps uppercase text-on-surface transition-colors duration-200 hover:border-outline hover:bg-surface-container-high aria-pressed:text-error [&>svg]:text-error disabled:cursor-not-allowed disabled:opacity-60";

// #FVS-WISHLIST-BUTTON (phase 6D)
//
// Saved state comes only from the canonical wishlist query (one list read
// for the whole page, never one request per product). Anonymous viewers get
// a sign-in link with the safe returnTo; there is no guest or local
// wishlist. Unverified viewers are pointed to verification (the backend
// would answer 403 EMAIL_VERIFICATION_REQUIRED). While the list is still
// loading the control is not offered, so it can never show a wrong state.
export function WishlistButton({ productId, productName, returnToPath, variant }: WishlistButtonProps) {
  const { user, isLoading } = useAuth();
  if (isLoading) return null;

  if (!user) {
    return (
      <a
        href={buildLoginRedirectPath(returnToPath)}
        aria-label={variant === "icon" ? `Sign in to save ${productName} to your wishlist` : undefined}
        className={variant === "icon" ? ICON_CLASS : FULL_CLASS}
      >
        <Heart filled={false} />
        {variant === "full" && <span>Save to wishlist</span>}
      </a>
    );
  }
  if (!user.emailVerified) {
    if (variant === "icon") return null;
    return (
      <p className="font-body text-body-md text-on-surface-variant">
        <Link href="/verify-email/resend" className="font-semibold text-primary underline underline-offset-4">
          Verify your email
        </Link>{" "}
        to save products to your wishlist.
      </p>
    );
  }
  return <VerifiedWishlistButton productId={productId} productName={productName} variant={variant} />;
}

function VerifiedWishlistButton({ productId, productName, variant }: Omit<WishlistButtonProps, "returnToPath">) {
  const queryClient = useQueryClient();
  const wishlist = useWishlist();
  const toggle = useToggleWishlist();
  const inFlight = useRef(false);
  const [error, setError] = useState<string | null>(null);

  if (!wishlist.data) return null;
  const saved = wishlist.data.some((item) => item.product_id === productId);
  const busy = toggle.isPending || wishlist.isFetching;

  async function handleClick() {
    // Not `disabled` while busy: a disabled button drops keyboard focus.
    if (inFlight.current || busy) return;
    inFlight.current = true;
    setError(null);
    try {
      await toggle.mutateAsync({ productId, save: !saved });
    } catch (failure) {
      const outcome = describeWishlistError(failure);
      if (outcome.refetchAuth) void queryClient.invalidateQueries({ queryKey: AUTH_SESSION_QUERY_KEY });
      setError(outcome.message);
    } finally {
      inFlight.current = false;
    }
  }

  // Icon: one constant name plus aria-pressed (a toggle). Full: no
  // aria-pressed; the visible text names the action, and a status line says
  // what is saved now.
  return (
    <span className={variant === "full" ? "flex w-full flex-col items-start gap-2" : "relative inline-flex"}>
      <button
        type="button"
        aria-pressed={variant === "icon" ? saved : undefined}
        aria-label={variant === "icon" ? `Save ${productName} to your wishlist` : undefined}
        aria-busy={busy || undefined}
        aria-disabled={busy || undefined}
        onClick={() => void handleClick()}
        className={`${variant === "icon" ? ICON_CLASS : FULL_CLASS} aria-disabled:opacity-60`}
      >
        <Heart filled={saved} />
        {variant === "full" && <span>{saved ? "Remove from wishlist" : "Save to wishlist"}</span>}
      </button>
      {variant === "full" && (
        <span role="status" className="font-body text-sm text-on-surface-variant">
          {saved ? (
            <>
              Saved to your{" "}
              <Link href="/account/wishlist" className="font-semibold text-primary underline underline-offset-4">
                wishlist
              </Link>
              .
            </>
          ) : null}
        </span>
      )}
      {error && (
        <span
          role="alert"
          className={
            variant === "full"
              ? "text-caption text-danger"
              : "absolute right-0 top-12 z-10 w-56 rounded-md border border-danger bg-danger-bg p-2 text-caption text-text-primary shadow-elevation-1"
          }
        >
          {error}
        </span>
      )}
    </span>
  );
}
