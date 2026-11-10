import { cartBlockingLines } from "@/lib/cart/cartInvariants";
import type { CartLineModel, CartModel } from "@/lib/cart/cartModel";
import type { MoneyModel, PublicSettingsModel } from "@/lib/settings/publicSettingsModel";
import type { CheckoutCartShape } from "./checkoutPayload";

// #SECURITY-CHECKOUT-SERVER-AUTHORITY
//
// What the checkout page offers, from the canonical cart and the public
// settings (backend 2dfb27b). Presentation only: the server re-checks the
// cart, the cash rules (enabled, every line physical, total within
// cash_max_order_total, blocks and open-order limits it never reveals) and
// pickup availability when the order is placed, and its answer wins.

export interface CashOption {
  // PublicSettings cash_payment_enabled.
  offered: boolean;
  // Offered AND every line is physical. The total cap cannot be checked
  // here: the cart has no authoritative total (live prices are applied at
  // checkout), so it is shown as information and enforced by the server.
  eligible: boolean;
  maxTotal: MoneyModel | null;
}

export function cashOption(cart: CheckoutCartShape, settings: PublicSettingsModel | undefined): CashOption {
  if (!settings?.cashPaymentEnabled) {
    return {
      offered: false,
      eligible: false,
      maxTotal: settings?.cashMaxOrderTotal ?? null,
    };
  }
  return {
    offered: true,
    eligible: cart.containsPhysical && !cart.containsDigital,
    maxTotal: settings.cashMaxOrderTotal,
  };
}

export interface PickupOption {
  // The server refuses pickup (422 INVALID_FULFILLMENT) without a pickup address.
  available: boolean;
  address: string | null;
  hours: string | null;
}

export function pickupOption(settings: PublicSettingsModel | undefined): PickupOption {
  return {
    available: Boolean(settings?.pickupAddress),
    address: settings?.pickupAddress ?? null,
    hours: settings?.pickupHours ?? null,
  };
}

export type CheckoutGate =
  | { kind: "ready" }
  | { kind: "verify-email" }
  | { kind: "empty" }
  | { kind: "needs-attention"; lines: readonly CartLineModel[] }
  | { kind: "paused" };

export function checkoutGate({
  user,
  cart,
  settings,
}: {
  user: { emailVerified: boolean };
  cart: CartModel;
  settings: PublicSettingsModel | undefined;
}): CheckoutGate {
  if (!user.emailVerified) {
    return { kind: "verify-email" };
  }
  if (cart.lines.length === 0) {
    return { kind: "empty" };
  }
  const blocking = cartBlockingLines(cart);
  if (blocking.length > 0) {
    return { kind: "needs-attention", lines: blocking };
  }
  if (settings && !settings.acceptingOrders) {
    return { kind: "paused" };
  }
  return { kind: "ready" };
}
