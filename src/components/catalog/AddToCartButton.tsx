import { buildLoginRedirectPath } from "@/lib/auth/returnTo";

export interface AddToCartButtonProps {
  isAuthenticated: boolean;
  returnToPath: string;
}

// #FVS014-ADD-TO-CART
//
// Resolves FVS-014-IMPLEMENTATION-PLAN.md §0's recorded source
// discrepancy by treating it as two different viewer states rather
// than a contradiction: an anonymous visitor's click needs no cart at
// all — it is a pure auth-gate redirect, safe to build now by reusing
// FVS-003's existing `buildLoginRedirectPath` (never a duplicated
// redirect-safety implementation). An authenticated visitor's click
// would need to actually add to a cart, which does not exist until
// FVS-025 — so for that viewer, nothing renders at all (hidden, not a
// disabled button with no accessible explanation to give, since "cart
// isn't built yet" is an engineering fact, not user-facing copy).
//
// No guest cart, no fake cart state, no placeholder POST request.
export function AddToCartButton({ isAuthenticated, returnToPath }: AddToCartButtonProps) {
  if (isAuthenticated) {
    return null;
  }

  return (
    <a
      href={buildLoginRedirectPath(returnToPath)}
      className="inline-block rounded-md bg-brand-dark-green px-4 py-2 text-text-on-brand"
    >
      Add to cart
    </a>
  );
}
