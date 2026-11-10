import { describe, expect, it } from "vitest";
import type { ApiError } from "@/lib/api/ApiError";
import { CHECKOUT_MESSAGES, describeCheckoutError } from "./checkoutErrors";

// Every Problem code POST /api/v1/checkout returns at backend 2dfb27b
// (ordering/api/checkout.py translate_checkout_error, in_progress_error,
// key_conflict_error, provider_failed; identity CSRF/verification deps;
// the shared rate limiter). Copy is frontend-owned: Problem.detail/title
// and ValidationError.msg must never come back out.

function http(
  status: number,
  code: string,
  extensions: Record<string, unknown> = {},
  extra: Partial<ApiError> = {}
): ApiError {
  return {
    kind: "http",
    status,
    code,
    title: "RAW TITLE",
    detail: "RAW DETAIL",
    message: "fallback",
    raw: {
      status,
      code,
      title: "RAW TITLE",
      detail: "RAW DETAIL",
      errors: [],
      ...extensions,
    },
    ...extra,
  };
}

function neverLeaksServerText(outcome: unknown) {
  const text = JSON.stringify(outcome);
  expect(text).not.toContain("RAW TITLE");
  expect(text).not.toContain("RAW DETAIL");
  expect(text).not.toContain("RAW MSG");
}

describe("describeCheckoutError", () => {
  it("409 CART_PRICE_CHANGED -> typed price changes, refetch the cart, nothing accepted automatically", () => {
    const outcome = describeCheckoutError(
      http(409, "CART_PRICE_CHANGED", {
        price_changes: [
          {
            product_id: "p-1",
            old_amount_cents: 1800,
            new_amount_cents: 2100,
            currency: "USD",
          },
          { product_id: "bad" },
        ],
      })
    );
    expect(outcome.kind).toBe("price-changed");
    expect(outcome.kind === "price-changed" && outcome.changes).toEqual([
      {
        productId: "p-1",
        oldAmountCents: 1800,
        newAmountCents: 2100,
        currency: "USD",
      },
    ]);
    expect(outcome.refetchCart).toBe(true);
    expect(outcome.uncertain).toBe(false);
    neverLeaksServerText(outcome);
  });

  it("422 PRODUCT_NOT_PURCHASABLE / QUANTITY_EXCEEDS_LIMIT -> refused lines with reason and max_quantity, refetch the cart", () => {
    const refused = describeCheckoutError(
      http(422, "PRODUCT_NOT_PURCHASABLE", {
        lines: [
          { product_id: "p-1", reason: "unavailable" },
          { product_id: "p-2", reason: "over_cap", max_quantity: 2 },
        ],
      })
    );
    expect(refused.kind === "lines-refused" && refused.lines).toEqual([
      { productId: "p-1", reason: "unavailable", maxQuantity: null },
      { productId: "p-2", reason: "over_cap", maxQuantity: 2 },
    ]);
    expect(refused.refetchCart).toBe(true);

    const caps = describeCheckoutError(
      http(422, "QUANTITY_EXCEEDS_LIMIT", {
        lines: [{ product_id: "p-3", reason: "over_cap", max_quantity: 1 }],
      })
    );
    expect(caps.kind).toBe("lines-refused");
  });

  it("409 PRODUCT_ALREADY_OWNED -> the product ids, refetch the cart", () => {
    const outcome = describeCheckoutError(http(409, "PRODUCT_ALREADY_OWNED", { product_ids: ["p-9", 4] }));
    expect(outcome.kind === "already-owned" && outcome.productIds).toEqual(["p-9"]);
    expect(outcome.refetchCart).toBe(true);
  });

  it("409 CART_EMPTY -> dropped (already owned) product ids, refetch the cart", () => {
    const outcome = describeCheckoutError(
      http(409, "CART_EMPTY", {
        dropped_lines: [{ product_id: "p-stl", reason: "already_owned" }],
      })
    );
    expect(outcome.kind === "cart-empty" && outcome.droppedProductIds).toEqual(["p-stl"]);
    expect(outcome.refetchCart).toBe(true);
  });

  it("422 VALIDATION_ERROR -> per-field frontend copy keyed by loc, never msg", () => {
    const outcome = describeCheckoutError(
      http(
        422,
        "VALIDATION_ERROR",
        {},
        {
          errors: [
            {
              loc: ["body", "contact_phone"],
              msg: "RAW MSG",
              type: "value_error",
            },
            {
              loc: ["body", "accept_cash_terms"],
              msg: "RAW MSG",
              type: "missing",
            },
          ],
        }
      )
    );
    expect(outcome.kind).toBe("fields");
    expect(outcome.kind === "fields" && outcome.fieldErrors).toEqual({
      contactPhone: CHECKOUT_MESSAGES.invalidPhone,
      acceptCashTerms: CHECKOUT_MESSAGES.cashTermsRequired,
    });
    neverLeaksServerText(outcome);
  });

  it("422 VALIDATION_ERROR with no recognised field -> a generic review message", () => {
    const outcome = describeCheckoutError(
      http(
        422,
        "VALIDATION_ERROR",
        {},
        {
          errors: [{ loc: ["header", "Idempotency-Key"], msg: "RAW MSG", type: "x" }],
        }
      )
    );
    expect(outcome.kind).toBe("message");
    expect(outcome.message).toBe(CHECKOUT_MESSAGES.invalidDetails);
  });

  it("422 INVALID_FULFILLMENT -> refetch addresses and settings", () => {
    const outcome = describeCheckoutError(http(422, "INVALID_FULFILLMENT"));
    expect(outcome.message).toBe(CHECKOUT_MESSAGES.invalidFulfillment);
    expect(outcome.refetchAddresses).toBe(true);
    expect(outcome.refetchSettings).toBe(true);
  });

  it.each([
    ["cash_requires_physical", CHECKOUT_MESSAGES.cashNeedsPhysical],
    ["cash_disabled", CHECKOUT_MESSAGES.cashDisabled],
    ["zero_total", CHECKOUT_MESSAGES.zeroTotal],
    ["provider_not_configured", CHECKOUT_MESSAGES.onlineUnavailable],
    ["provider_required", CHECKOUT_MESSAGES.onlineUnavailable],
    ["provider_not_applicable", CHECKOUT_MESSAGES.generic],
    ["something_new", CHECKOUT_MESSAGES.paymentNotAllowed],
  ])("422 PAYMENT_METHOD_NOT_ALLOWED reason %s", (reason, message) => {
    const outcome = describeCheckoutError(http(422, "PAYMENT_METHOD_NOT_ALLOWED", { reason }));
    expect(outcome.message).toBe(message);
  });

  it("422 CASH_PAYMENT_LIMIT_REACHED names the public cash limit when known", () => {
    expect(
      describeCheckoutError(http(422, "CASH_PAYMENT_LIMIT_REACHED", { reason: "order_total" }), {
        cashMaxOrderTotal: { amountCents: 10000, currency: "USD" },
      }).message
    ).toBe("This order is above the $100.00 limit for cash payment. Please pay online.");
    expect(describeCheckoutError(http(422, "CASH_PAYMENT_LIMIT_REACHED", { reason: "order_total" })).message).toBe(
      CHECKOUT_MESSAGES.cashLimit
    );
  });

  it("422 CASH_NOT_AVAILABLE never says why (the backend deliberately hides it)", () => {
    expect(describeCheckoutError(http(422, "CASH_NOT_AVAILABLE")).message).toBe(CHECKOUT_MESSAGES.cashNotAvailable);
  });

  it("409 IDEMPOTENCY_REQUEST_IN_PROGRESS is uncertain: keep the key, offer a same-key re-check", () => {
    const outcome = describeCheckoutError(
      http(409, "IDEMPOTENCY_REQUEST_IN_PROGRESS", { order_id: "o-1", order_number: "B3D-1" }, { retryAfterSeconds: 2 })
    );
    expect(outcome.uncertain).toBe(true);
    expect(outcome.retireKey).toBe(false);
    expect(outcome.message).toBe(CHECKOUT_MESSAGES.inProgress);
  });

  it("409 IDEMPOTENCY_KEY_CONFLICT retires the key", () => {
    const outcome = describeCheckoutError(http(409, "IDEMPOTENCY_KEY_CONFLICT"));
    expect(outcome.retireKey).toBe(true);
    expect(outcome.uncertain).toBe(false);
  });

  it("502 PAYMENT_PROVIDER_UNAVAILABLE: the order exists unpaid and the cart was cleared", () => {
    const outcome = describeCheckoutError(
      http(502, "PAYMENT_PROVIDER_UNAVAILABLE", {
        order_id: "o-1",
        order_number: "B3D-2026-000777",
      })
    );
    expect(outcome.kind === "payment-not-started" && outcome.orderNumber).toBe("B3D-2026-000777");
    expect(outcome.refetchCart).toBe(true);
    expect(outcome.retireKey).toBe(true);
  });

  it.each([
    [{ kind: "network", message: "x", raw: undefined } as ApiError],
    [{ kind: "timeout", message: "x", raw: undefined } as ApiError],
    [{ kind: "parse", message: "x", raw: "<html>" } as ApiError],
    [http(500, "INTERNAL_ERROR")],
    [http(504, "")],
  ])("an unknown outcome (%o) is uncertain: same-key retry, the cart is NOT refetched", (error) => {
    const outcome = describeCheckoutError(error);
    expect(outcome.uncertain).toBe(true);
    expect(outcome.refetchCart).toBe(false);
    expect(outcome.message).toBe(CHECKOUT_MESSAGES.uncertain);
  });

  it("CSRF (local or 403 CSRF_INVALID), email verification, session expiry, rate limit, pauses", () => {
    expect(describeCheckoutError({ kind: "csrf", message: "x", raw: undefined }).message).toBe(CHECKOUT_MESSAGES.csrf);
    expect(describeCheckoutError(http(403, "CSRF_INVALID")).message).toBe(CHECKOUT_MESSAGES.csrf);
    const verify = describeCheckoutError(http(403, "EMAIL_VERIFICATION_REQUIRED"));
    expect(verify.kind).toBe("verify-email");
    expect(verify.refetchAuth).toBe(true);
    expect(describeCheckoutError(http(401, "AUTH_REQUIRED")).kind).toBe("session-expired");
    expect(describeCheckoutError(http(429, "RATE_LIMITED", {}, { retryAfterSeconds: 1800 })).message).toBe(
      "Too many checkout attempts. Please try again in 30 minutes."
    );
    expect(describeCheckoutError(http(429, "RATE_LIMITED")).message).toBe(CHECKOUT_MESSAGES.rateLimited);
    const paused = describeCheckoutError(http(503, "ORDERS_PAUSED"));
    expect(paused.message).toBe(CHECKOUT_MESSAGES.ordersPaused);
    expect(paused.refetchSettings).toBe(true);
    expect(describeCheckoutError(http(503, "ONLINE_PAYMENT_UNAVAILABLE")).message).toBe(
      CHECKOUT_MESSAGES.onlineUnavailable
    );
  });

  it("anything unrecognised is a definitive generic failure that keeps the cart", () => {
    const outcome = describeCheckoutError(http(400, "SOMETHING_ELSE"));
    expect(outcome).toMatchObject({
      kind: "message",
      message: CHECKOUT_MESSAGES.generic,
      refetchCart: false,
      uncertain: false,
    });
    expect(describeCheckoutError(new Error("boom")).message).toBe(CHECKOUT_MESSAGES.generic);
  });
});
