// Frontend-owned checkout copy (FVS-026). Nothing here is server text.

// PENDING LEGAL REVIEW — the consent wording below is working copy so the
// checkout is usable. It is NOT approved legal text (open item Q8 in
// docs/backend-handoff/CURRENT-BACKEND-DRIFT-AUDIT.md). The backend only
// requires the booleans: accept_terms (always), accept_digital_final_sale
// (while an STL line remains) and accept_cash_terms (cash). Do not add
// further consent checkboxes: the contract has no field for them.
export const CONSENT_COPY = {
  terms: "I agree to the Bekaa3D terms of sale for this order.",
  digitalFinalSale:
    "I understand that STL files are digital products sold as final sale: an STL purchase can't be cancelled or returned.",
  cashTerms: "I agree to pay the full amount in cash to the courier on delivery, or at pickup.",
} as const;

// ADR-024: the website charges no shipping. The courier sets and collects
// the delivery fee separately. No zones, no threshold, no estimate.
export const FULFILLMENT_COPY = {
  deliveryHint: "We hand your order to a courier. The website doesn't charge for delivery.",
  courierFee:
    "The courier sets the delivery fee and you pay it to them directly on delivery. It isn't part of your order total.",
  pickupHint: "Collect your order from us. There's no delivery fee.",
  digitalOnly:
    "Your order only has STL files, so there's nothing to deliver. You'll be able to download them once your payment is confirmed.",
  mixedDigital:
    "STL files in this order aren't delivered: you'll be able to download them once your payment is confirmed.",
} as const;

export const PAYMENT_COPY = {
  onlineLabel: "Pay online",
  onlineHint:
    "You'll continue to the payment page after placing your order. Your order counts as paid only once the payment is confirmed.",
  cashLabel: "Pay in cash",
  cashHint: "Pay the courier on delivery, or pay when you pick up your order.",
  cashNeedsPhysical:
    "Cash isn't available because this order includes STL files. Cash is only for orders of physical items.",
} as const;

// Why a line can't be checked out (PurchaseRefusal + over_cap).
export function refusalReasonText(reason: string, maxQuantity: number | null): string {
  switch (reason) {
    case "unavailable":
      return "is currently unavailable.";
    case "whatsapp_only":
      return "can only be ordered through WhatsApp.";
    case "not_listed":
      return "is no longer available.";
    case "over_cap":
      return maxQuantity !== null && maxQuantity > 0
        ? `is limited to ${maxQuantity} per order. Reduce the quantity in your cart.`
        : "is above its quantity limit. Reduce the quantity in your cart.";
    default:
      return "can't be ordered right now.";
  }
}
