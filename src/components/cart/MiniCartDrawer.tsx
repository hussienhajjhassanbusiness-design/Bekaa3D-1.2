"use client";

import { useId } from "react";
import { DialogShell } from "@/components/feedback/DialogShell";
import { LoggedOutCartPrompt } from "./LoggedOutCartPrompt";
import { CartPage } from "./CartPage";
import type { CartModel } from "@/lib/cart/cartModel";

export interface MiniCartDrawerProps {
  open: boolean;
  onClose: () => void;
  isAuthenticated: boolean;
  cart: CartModel | null;
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
  onQuantityChange: (lineId: string, nextQuantity: number) => void;
  onRemove: (lineId: string) => void;
}

// Bottom sheet on mobile, right-side slide-over at tablet and above —
// `fixed` positioning escapes DialogShell's centering backdrop
// entirely, so no change to the backdrop/focus-trap logic was needed.
const DRAWER_PANEL_CLASSNAME =
  "fixed inset-x-0 bottom-0 max-h-[80vh] w-full overflow-y-auto rounded-t-lg bg-white p-6 shadow-elevation-3 tablet:inset-y-0 tablet:bottom-auto tablet:left-auto tablet:right-0 tablet:h-full tablet:max-h-full tablet:w-96 tablet:rounded-t-none tablet:rounded-l-lg";

// #FVS025-MINI-CART-DRAWER
//
// Reuses DialogShell's real focus-trap/Escape/backdrop via its
// panelClassName seam — zero new focus-trap code
// (FRONTEND-VERTICAL-SLICE-PLAN.md's "audit DialogShell before
// inventing another focus trap" instruction). Anonymous state renders
// LoggedOutCartPrompt (resolving the /cart route-vs-drawer
// discrepancy, plan §0); authenticated state reuses CartPage's exact
// presentation so there is only ever one cart rendering path.
export function MiniCartDrawer({
  open,
  onClose,
  isAuthenticated,
  cart,
  isLoading,
  isError,
  errorMessage,
  onRetry,
  onQuantityChange,
  onRemove,
}: MiniCartDrawerProps) {
  const titleId = useId();

  return (
    <DialogShell open={open} onClose={onClose} labelledBy={titleId} panelClassName={DRAWER_PANEL_CLASSNAME}>
      <h2 id={titleId} className="text-h3 font-bold text-text-primary">
        Cart
      </h2>
      <div className="mt-4">
        {isAuthenticated ? (
          <CartPage
            cart={cart}
            isLoading={isLoading}
            isError={isError}
            errorMessage={errorMessage}
            onRetry={onRetry}
            onQuantityChange={onQuantityChange}
            onRemove={onRemove}
          />
        ) : (
          <LoggedOutCartPrompt />
        )}
      </div>
    </DialogShell>
  );
}
