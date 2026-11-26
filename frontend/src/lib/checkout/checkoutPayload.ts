import type { AcceptedPriceDTO, CheckoutRequestDTO, FulfillmentMethod, PaymentMethod } from "./checkoutTypes";

// #ARCHITECTURE-CHECKOUT-REQUEST-ADAPTER
//
// The single place a POST /api/v1/checkout body is built (see
// checkoutTypes.ts for the contract). The builder only emits fields the
// fulfillment matrix allows for this cart, so a stale form value (an
// address picked before switching to pickup, say) can never leak into the
// request. validateCheckoutForm is UX feedback only: the server still
// re-validates everything and its answer wins.

export interface CheckoutFormState {
  fulfillment: FulfillmentMethod | null;
  addressId: string | null;
  contactPhone: string;
  paymentMethod: PaymentMethod | null;
  acceptTerms: boolean;
  acceptDigitalFinalSale: boolean;
  acceptCashTerms: boolean;
  customerNote: string;
}

// Every consent starts unticked; nothing is pre-chosen except what the
// container fills in from the customer's own data (their default address).
export const EMPTY_CHECKOUT_FORM: CheckoutFormState = {
  fulfillment: null,
  addressId: null,
  contactPhone: "",
  paymentMethod: null,
  acceptTerms: false,
  acceptDigitalFinalSale: false,
  acceptCashTerms: false,
  customerNote: "",
};

export interface CheckoutCartShape {
  containsPhysical: boolean;
  containsDigital: boolean;
}

export interface CheckoutAvailability {
  // public settings cash_payment_enabled
  cashOffered: boolean;
  // public settings pickup_address is set (the server refuses pickup otherwise)
  pickupAvailable: boolean;
}

// A price the customer explicitly accepted after a 409 CART_PRICE_CHANGED.
export interface AcceptedPrice {
  productId: string;
  amountCents: number;
  currency: string;
}

export type CheckoutFieldKey = keyof CheckoutFormState;
export type CheckoutFieldErrors = Partial<Record<CheckoutFieldKey, string>>;

export const MAX_CUSTOMER_NOTE = 1000;
export const MAX_CONTACT_PHONE = 32;
// AcceptedPriceIn list max_length (checkout_schemas.py MAX_ACCEPTED_PRICES).
export const MAX_ACCEPTED_PRICES = 50;

export const PAYLOAD_MESSAGES = {
  fulfillmentRequired: "Choose delivery or pickup.",
  pickupUnavailable: "Pickup isn't available right now. Please choose delivery.",
  addressRequired: "Choose a delivery address.",
  phoneRequired: "Enter a phone number we can reach you on for pickup.",
  phoneTooLong: "That phone number is too long.",
  paymentRequired: "Choose how you'd like to pay.",
  cashUnavailable: "Cash payment isn't available right now. Please pay online.",
  cashNeedsPhysical: "Cash is only available when every item in your order is a physical product.",
  termsRequired: "Please accept the terms of sale to place your order.",
  digitalRequired: "Please confirm you understand that STL files are final sale.",
  cashTermsRequired: "Please accept the cash payment terms.",
  noteTooLong: `Notes can be at most ${MAX_CUSTOMER_NOTE} characters.`,
} as const;

export function validateCheckoutForm(
  form: CheckoutFormState,
  cart: CheckoutCartShape,
  availability: CheckoutAvailability
): CheckoutFieldErrors {
  const errors: CheckoutFieldErrors = {};

  if (cart.containsPhysical) {
    if (form.fulfillment === null) {
      errors.fulfillment = PAYLOAD_MESSAGES.fulfillmentRequired;
    } else if (form.fulfillment === "pickup" && !availability.pickupAvailable) {
      errors.fulfillment = PAYLOAD_MESSAGES.pickupUnavailable;
    } else if (form.fulfillment === "delivery" && !form.addressId) {
      errors.addressId = PAYLOAD_MESSAGES.addressRequired;
    } else if (form.fulfillment === "pickup") {
      const phone = form.contactPhone.trim();
      if (phone === "") {
        errors.contactPhone = PAYLOAD_MESSAGES.phoneRequired;
      } else if (phone.length > MAX_CONTACT_PHONE) {
        errors.contactPhone = PAYLOAD_MESSAGES.phoneTooLong;
      }
    }
  }

  if (form.paymentMethod === null) {
    errors.paymentMethod = PAYLOAD_MESSAGES.paymentRequired;
  } else if (form.paymentMethod === "cash") {
    if (!availability.cashOffered) {
      errors.paymentMethod = PAYLOAD_MESSAGES.cashUnavailable;
    } else if (!cart.containsPhysical || cart.containsDigital) {
      errors.paymentMethod = PAYLOAD_MESSAGES.cashNeedsPhysical;
    } else if (!form.acceptCashTerms) {
      errors.acceptCashTerms = PAYLOAD_MESSAGES.cashTermsRequired;
    }
  }

  if (!form.acceptTerms) {
    errors.acceptTerms = PAYLOAD_MESSAGES.termsRequired;
  }
  if (cart.containsDigital && !form.acceptDigitalFinalSale) {
    errors.acceptDigitalFinalSale = PAYLOAD_MESSAGES.digitalRequired;
  }
  if (form.customerNote.trim().length > MAX_CUSTOMER_NOTE) {
    errors.customerNote = PAYLOAD_MESSAGES.noteTooLong;
  }
  return errors;
}

// Newest acceptance wins per product (replaced in place); new products are
// appended. Capped at the contract maximum, dropping the oldest first.
export function mergeAcceptedPrices(
  previous: readonly AcceptedPrice[],
  accepted: readonly AcceptedPrice[]
): AcceptedPrice[] {
  const latest = new Map(accepted.map((entry) => [entry.productId, entry]));
  const merged = previous.map((entry) => latest.get(entry.productId) ?? entry);
  const known = new Set(previous.map((entry) => entry.productId));
  merged.push(...accepted.filter((entry) => !known.has(entry.productId)));
  return merged.slice(Math.max(0, merged.length - MAX_ACCEPTED_PRICES));
}

function toAcceptedPriceDTO(entry: AcceptedPrice): AcceptedPriceDTO {
  return {
    product_id: entry.productId,
    amount_cents: entry.amountCents,
    currency: entry.currency,
  };
}

export function buildCheckoutRequest(
  form: CheckoutFormState,
  cart: CheckoutCartShape,
  acceptedPrices: readonly AcceptedPrice[]
): CheckoutRequestDTO {
  if (form.paymentMethod === null) {
    throw new Error("buildCheckoutRequest: validate the form before building a request");
  }

  const body: CheckoutRequestDTO = {
    payment_method: form.paymentMethod,
    accept_terms: true,
  };

  if (cart.containsPhysical && form.fulfillment !== null) {
    body.fulfillment_method = form.fulfillment;
    if (form.fulfillment === "delivery" && form.addressId) {
      body.address_id = form.addressId;
    }
    if (form.fulfillment === "pickup") {
      body.contact_phone = form.contactPhone.trim();
    }
  }

  const note = form.customerNote.trim();
  if (note !== "") {
    body.customer_note = note;
  }
  if (cart.containsDigital && form.acceptDigitalFinalSale) {
    body.accept_digital_final_sale = true;
  }
  if (form.paymentMethod === "cash" && form.acceptCashTerms) {
    body.accept_cash_terms = true;
  }
  if (acceptedPrices.length > 0) {
    body.accepted_price_changes = acceptedPrices.map(toAcceptedPriceDTO);
  }
  return body;
}
