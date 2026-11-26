import { describe, expect, it } from "vitest";
import {
  EMPTY_CHECKOUT_FORM,
  PAYLOAD_MESSAGES,
  buildCheckoutRequest,
  mergeAcceptedPrices,
  validateCheckoutForm,
  type CheckoutFormState,
} from "./checkoutPayload";

// #ARCHITECTURE-CHECKOUT-REQUEST-ADAPTER — the one place a CheckoutRequest
// body is built. Exact field set per backend 2dfb27b checkout_schemas.py +
// domain/fulfillment.py; validation here is UX only (the server decides).

const PHYSICAL = { containsPhysical: true, containsDigital: false };
const STL = { containsPhysical: false, containsDigital: true };
const MIXED = { containsPhysical: true, containsDigital: true };
const CASH_ON = { cashOffered: true, pickupAvailable: true };
const CASH_OFF = { cashOffered: false, pickupAvailable: false };

function form(overrides: Partial<CheckoutFormState>): CheckoutFormState {
  return { ...EMPTY_CHECKOUT_FORM, acceptTerms: true, ...overrides };
}

describe("buildCheckoutRequest", () => {
  it("physical + delivery: address_id, NO contact_phone, accept_terms only", () => {
    const body = buildCheckoutRequest(
      form({
        fulfillment: "delivery",
        addressId: "a-1",
        contactPhone: "70 123 456",
        paymentMethod: "online",
      }),
      PHYSICAL,
      []
    );
    expect(body).toEqual({
      payment_method: "online",
      fulfillment_method: "delivery",
      address_id: "a-1",
      accept_terms: true,
    });
  });

  it("physical + pickup: trimmed contact_phone, NO address_id", () => {
    const body = buildCheckoutRequest(
      form({
        fulfillment: "pickup",
        addressId: "a-1",
        contactPhone: "  70 123 456 ",
        paymentMethod: "online",
      }),
      PHYSICAL,
      []
    );
    expect(body).toEqual({
      payment_method: "online",
      fulfillment_method: "pickup",
      contact_phone: "70 123 456",
      accept_terms: true,
    });
  });

  it("STL only: no fulfillment fields at all, even if stale form values exist, and accept_digital_final_sale: true", () => {
    const body = buildCheckoutRequest(
      form({
        fulfillment: "delivery",
        addressId: "a-1",
        contactPhone: "70123456",
        paymentMethod: "online",
        acceptDigitalFinalSale: true,
      }),
      STL,
      []
    );
    expect(body).toEqual({
      payment_method: "online",
      accept_terms: true,
      accept_digital_final_sale: true,
    });
    expect(body).not.toHaveProperty("fulfillment_method");
    expect(body).not.toHaveProperty("address_id");
    expect(body).not.toHaveProperty("contact_phone");
  });

  it("mixed: delivery fields plus accept_digital_final_sale", () => {
    const body = buildCheckoutRequest(
      form({
        fulfillment: "delivery",
        addressId: "a-2",
        paymentMethod: "online",
        acceptDigitalFinalSale: true,
      }),
      MIXED,
      []
    );
    expect(body).toEqual({
      payment_method: "online",
      fulfillment_method: "delivery",
      address_id: "a-2",
      accept_terms: true,
      accept_digital_final_sale: true,
    });
  });

  it("cash: accept_cash_terms: true; online never sends accept_cash_terms even if ticked", () => {
    const cash = buildCheckoutRequest(
      form({
        fulfillment: "delivery",
        addressId: "a-1",
        paymentMethod: "cash",
        acceptCashTerms: true,
      }),
      PHYSICAL,
      []
    );
    expect(cash.accept_cash_terms).toBe(true);
    expect(cash.payment_method).toBe("cash");

    const online = buildCheckoutRequest(
      form({
        fulfillment: "delivery",
        addressId: "a-1",
        paymentMethod: "online",
        acceptCashTerms: true,
      }),
      PHYSICAL,
      []
    );
    expect(online).not.toHaveProperty("accept_cash_terms");
  });

  it("never sends payment_provider, an amount, a total or a price", () => {
    const body = buildCheckoutRequest(
      form({
        fulfillment: "delivery",
        addressId: "a-1",
        paymentMethod: "online",
      }),
      PHYSICAL,
      []
    ) as unknown as Record<string, unknown>;
    for (const key of ["payment_provider", "total", "amount_cents", "subtotal", "price"]) {
      expect(body).not.toHaveProperty(key);
    }
  });

  it("customer_note is trimmed and omitted when blank", () => {
    const withNote = buildCheckoutRequest(
      form({
        fulfillment: "delivery",
        addressId: "a-1",
        paymentMethod: "online",
        customerNote: "  ring twice  ",
      }),
      PHYSICAL,
      []
    );
    expect(withNote.customer_note).toBe("ring twice");
    const blank = buildCheckoutRequest(
      form({
        fulfillment: "delivery",
        addressId: "a-1",
        paymentMethod: "online",
        customerNote: "   ",
      }),
      PHYSICAL,
      []
    );
    expect(blank).not.toHaveProperty("customer_note");
  });

  it("accepted_price_changes are sent exactly as accepted (product_id, amount_cents, currency) and omitted when none", () => {
    const body = buildCheckoutRequest(
      form({
        fulfillment: "delivery",
        addressId: "a-1",
        paymentMethod: "online",
      }),
      PHYSICAL,
      [{ productId: "p-1", amountCents: 2100, currency: "USD" }]
    );
    expect(body.accepted_price_changes).toEqual([{ product_id: "p-1", amount_cents: 2100, currency: "USD" }]);

    const none = buildCheckoutRequest(
      form({
        fulfillment: "delivery",
        addressId: "a-1",
        paymentMethod: "online",
      }),
      PHYSICAL,
      []
    );
    expect(none).not.toHaveProperty("accepted_price_changes");
  });

  it("throws rather than build a body with no payment method (callers validate first)", () => {
    expect(() => buildCheckoutRequest(form({}), STL, [])).toThrow();
  });
});

describe("mergeAcceptedPrices", () => {
  it("adds newly accepted prices and replaces an older acceptance for the same product", () => {
    const merged = mergeAcceptedPrices(
      [
        { productId: "p-1", amountCents: 2000, currency: "USD" },
        { productId: "p-2", amountCents: 500, currency: "USD" },
      ],
      [{ productId: "p-1", amountCents: 2200, currency: "USD" }]
    );
    expect(merged).toEqual([
      { productId: "p-1", amountCents: 2200, currency: "USD" },
      { productId: "p-2", amountCents: 500, currency: "USD" },
    ]);
  });

  it("never exceeds the contract's 50-entry maximum (newest kept)", () => {
    const old = Array.from({ length: 50 }, (_, i) => ({
      productId: `old-${i}`,
      amountCents: i,
      currency: "USD",
    }));
    const merged = mergeAcceptedPrices(old, [{ productId: "new", amountCents: 1, currency: "USD" }]);
    expect(merged).toHaveLength(50);
    expect(merged.some((entry) => entry.productId === "new")).toBe(true);
  });
});

describe("validateCheckoutForm (UX only)", () => {
  it("an untouched form reports every missing choice for a mixed cart", () => {
    const errors = validateCheckoutForm({ ...EMPTY_CHECKOUT_FORM }, MIXED, CASH_ON);
    expect(errors).toEqual({
      fulfillment: PAYLOAD_MESSAGES.fulfillmentRequired,
      paymentMethod: PAYLOAD_MESSAGES.paymentRequired,
      acceptTerms: PAYLOAD_MESSAGES.termsRequired,
      acceptDigitalFinalSale: PAYLOAD_MESSAGES.digitalRequired,
    });
  });

  it("delivery needs an address; pickup needs a contact phone", () => {
    expect(validateCheckoutForm(form({ fulfillment: "delivery", paymentMethod: "online" }), PHYSICAL, CASH_ON)).toEqual(
      {
        addressId: PAYLOAD_MESSAGES.addressRequired,
      }
    );
    expect(
      validateCheckoutForm(
        form({
          fulfillment: "pickup",
          contactPhone: "  ",
          paymentMethod: "online",
        }),
        PHYSICAL,
        CASH_ON
      )
    ).toEqual({ contactPhone: PAYLOAD_MESSAGES.phoneRequired });
  });

  it("pickup is refused locally when the shop has no pickup address configured", () => {
    expect(
      validateCheckoutForm(
        form({
          fulfillment: "pickup",
          contactPhone: "70123456",
          paymentMethod: "online",
        }),
        PHYSICAL,
        CASH_OFF
      )
    ).toEqual({ fulfillment: PAYLOAD_MESSAGES.pickupUnavailable });
  });

  it("cash: needs the cash terms, a physical-only cart, and cash to be offered", () => {
    expect(
      validateCheckoutForm(
        form({
          fulfillment: "delivery",
          addressId: "a",
          paymentMethod: "cash",
        }),
        PHYSICAL,
        CASH_ON
      )
    ).toEqual({ acceptCashTerms: PAYLOAD_MESSAGES.cashTermsRequired });
    expect(
      validateCheckoutForm(
        form({
          fulfillment: "delivery",
          addressId: "a",
          paymentMethod: "cash",
          acceptCashTerms: true,
          acceptDigitalFinalSale: true,
        }),
        MIXED,
        CASH_ON
      )
    ).toEqual({ paymentMethod: PAYLOAD_MESSAGES.cashNeedsPhysical });
    expect(
      validateCheckoutForm(
        form({
          fulfillment: "delivery",
          addressId: "a",
          paymentMethod: "cash",
          acceptCashTerms: true,
        }),
        PHYSICAL,
        CASH_OFF
      )
    ).toEqual({ paymentMethod: PAYLOAD_MESSAGES.cashUnavailable });
  });

  it("a note over 1000 characters is flagged", () => {
    expect(
      validateCheckoutForm(
        form({
          fulfillment: "delivery",
          addressId: "a",
          paymentMethod: "online",
          customerNote: "x".repeat(1001),
        }),
        PHYSICAL,
        CASH_ON
      )
    ).toEqual({ customerNote: PAYLOAD_MESSAGES.noteTooLong });
  });

  it("STL only: no fulfillment is asked for", () => {
    expect(validateCheckoutForm(form({ paymentMethod: "online", acceptDigitalFinalSale: true }), STL, CASH_ON)).toEqual(
      {}
    );
  });
});
