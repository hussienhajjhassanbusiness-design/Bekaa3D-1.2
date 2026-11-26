import { describe, it, expect, vi, afterEach } from "vitest";
import { apiClient } from "@/lib/api/apiClient";
import type { ApiError } from "@/lib/api/ApiError";
import { offersAdminApi } from "@/lib/admin/offers/offersAdminApi";
import { createCheckoutAttemptTracker } from "@/lib/checkout/checkoutIdempotency";
import { describeOfferCheckoutError, describeOfferError, OFFER_CHECKOUT_MESSAGES, OFFER_MESSAGES } from "./offerErrors";
import { OFFER_ID, OFFER_PRODUCT_ID, offerDetail } from "./offerFixtures";
import { allowedMoves, describeOfferStatus, describeRound, isLiveOffer, offerDeadline } from "./offerModel";
import { offersApi } from "./offersApi";

afterEach(() => vi.restoreAllMocks());

function http(status: number, code: string, extra: Record<string, unknown> = {}, more: Partial<ApiError> = {}): ApiError {
  return { kind: "http", status, code, title: "RAW TITLE", detail: "RAW DETAIL", message: "RAW", raw: { code, ...extra }, ...more };
}

describe("offersApi (customer)", () => {
  it("uses the exact routes, bodies and CSRF", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ items: [], next_cursor: null });
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(offerDetail());
    await offersApi.listMyOffers({ productId: OFFER_PRODUCT_ID, limit: 5, cursor: "c1" });
    await offersApi.listMyOffers();
    await offersApi.getMyOffer(OFFER_ID);
    await offersApi.createOffer({ productId: OFFER_PRODUCT_ID, amountCents: 1500, message: "  hi  " });
    await offersApi.createOffer({ productId: OFFER_PRODUCT_ID, amountCents: 1500, message: "   " });
    await offersApi.counterOffer(OFFER_ID, 1700);
    await offersApi.acceptOffer(OFFER_ID, 1700);
    await offersApi.withdrawOffer(OFFER_ID);
    await offersApi.withdrawOffer(OFFER_ID, "changed my mind");
    expect(get.mock.calls).toEqual([
      [`/api/v1/me/offers?product_id=${OFFER_PRODUCT_ID}&cursor=c1&limit=5`],
      ["/api/v1/me/offers"],
      [`/api/v1/me/offers/${OFFER_ID}`],
    ]);
    expect(post.mock.calls).toEqual([
      ["/api/v1/offers", { product_id: OFFER_PRODUCT_ID, amount_cents: 1500, currency: "USD", message: "hi" }, { csrf: true }],
      ["/api/v1/offers", { product_id: OFFER_PRODUCT_ID, amount_cents: 1500, currency: "USD" }, { csrf: true }],
      [`/api/v1/me/offers/${OFFER_ID}/counter`, { amount_cents: 1700, currency: "USD" }, { csrf: true }],
      [`/api/v1/me/offers/${OFFER_ID}/accept`, { expected_amount_cents: 1700 }, { csrf: true }],
      [`/api/v1/me/offers/${OFFER_ID}/withdraw`, undefined, { csrf: true }],
      [`/api/v1/me/offers/${OFFER_ID}/withdraw`, { reason: "changed my mind" }, { csrf: true }],
    ]);
  });

  it("checks out with both consents, the Idempotency-Key and the long timeout", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({});
    await offersApi.checkoutOffer(OFFER_ID, "key-12345678");
    expect(post).toHaveBeenCalledWith(
      `/api/v1/me/offers/${OFFER_ID}/checkout`,
      { accept_terms: true, accept_digital_final_sale: true },
      { csrf: true, headers: { "Idempotency-Key": "key-12345678" }, timeoutMs: 30_000 }
    );
  });

  it("reuses one key for the fixed offer-checkout body until it is retired", () => {
    let n = 0;
    const tracker = createCheckoutAttemptTracker<{ accept_terms: true }>(() => `generated-${++n}`);
    const a = tracker.keyFor({ accept_terms: true });
    expect(tracker.keyFor({ accept_terms: true })).toBe(a);
    tracker.retire();
    expect(tracker.keyFor({ accept_terms: true })).not.toBe(a);
  });
});

describe("offersAdminApi", () => {
  it("uses the exact admin routes, bodies and CSRF", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ items: [], next_cursor: null });
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(offerDetail());
    await offersAdminApi.listOffers({ status: "awaiting_admin", cursor: "c2" });
    await offersAdminApi.listOffers({});
    await offersAdminApi.getOffer(OFFER_ID);
    await offersAdminApi.acceptOffer(OFFER_ID, 1500);
    await offersAdminApi.counterOffer(OFFER_ID, 1800, "Best I can do");
    await offersAdminApi.rejectOffer(OFFER_ID);
    expect(get.mock.calls).toEqual([
      ["/api/v1/admin/offers?status=awaiting_admin&cursor=c2"],
      ["/api/v1/admin/offers"],
      [`/api/v1/admin/offers/${OFFER_ID}`],
    ]);
    expect(post.mock.calls).toEqual([
      [`/api/v1/admin/offers/${OFFER_ID}/accept`, { expected_amount_cents: 1500 }, { csrf: true }],
      [`/api/v1/admin/offers/${OFFER_ID}/counter`, { amount_cents: 1800, currency: "USD", message: "Best I can do" }, { csrf: true }],
      [`/api/v1/admin/offers/${OFFER_ID}/reject`, undefined, { csrf: true }],
    ]);
  });
});

describe("offerModel", () => {
  it("labels every status per perspective and treats unknown values neutrally", () => {
    expect(describeOfferStatus("awaiting_customer", "customer")).toEqual({ label: "Your reply needed", tone: "warning" });
    expect(describeOfferStatus("awaiting_admin", "admin")).toEqual({ label: "Your reply needed", tone: "warning" });
    expect(describeOfferStatus("something_new", "customer")).toEqual({ label: "Status unavailable", tone: "neutral" });
  });

  it("keeps only the caller's own server-allowed moves, in a fixed order", () => {
    expect(allowedMoves(["withdraw", "counter", "accept"], "customer")).toEqual(["accept", "counter", "withdraw"]);
    expect(allowedMoves(["reject", "withdraw", "teleport"], "admin")).toEqual(["reject"]);
    expect(allowedMoves([], "customer")).toEqual([]);
  });

  it("knows the live statuses that block a new offer", () => {
    expect(["awaiting_admin", "awaiting_customer", "accepted"].every(isLiveOffer)).toBe(true);
    expect(["rejected", "expired", "withdrawn", "paid", "checkout_expired", "auto_closed"].some(isLiveOffer)).toBe(false);
  });

  it("describes rounds from the viewer's side", () => {
    const round = offerDetail().rounds[0]!;
    expect(describeRound(round, "customer")).toBe("You offered $15.00");
    expect(describeRound(round, "admin")).toBe("Customer offered $15.00");
    expect(describeRound({ ...round, actor: "admin", action: "countered", amount: { amount_cents: 1800, currency: "USD" } }, "customer")).toBe(
      "Bekaa3D countered with $18.00"
    );
    expect(describeRound({ ...round, actor: "system", action: "expired", amount: null }, "customer")).toMatch(/expired/);
  });

  it("picks the deadline that applies now", () => {
    expect(offerDeadline(offerDetail())).toEqual({ kind: "reply", at: "2026-11-14T10:00:00Z" });
    expect(offerDeadline(offerDetail({ status: "accepted", responds_by: null, checkout_expires_at: "2026-11-13T10:00:00Z" }))).toEqual({
      kind: "checkout",
      at: "2026-11-13T10:00:00Z",
    });
    expect(offerDeadline(offerDetail({ status: "expired" }))).toBeNull();
  });
});

describe("describeOfferError", () => {
  it("never returns the server's title/detail/msg", () => {
    const all = [
      http(409, "OFFER_ALREADY_ACTIVE"),
      http(422, "VALIDATION_ERROR", {}, { errors: [{ loc: ["body", "amount_cents"], msg: "RAW MSG", type: "value_error" }] }),
      http(409, "SOMETHING_NEW"),
    ];
    for (const error of all) {
      const outcome = describeOfferError(error, "create");
      expect(outcome.message).not.toMatch(/RAW/);
    }
  });

  it("shows the server's minimum and cooldown from typed extensions", () => {
    const below = describeOfferError(http(422, "OFFER_BELOW_MINIMUM", { minimum: { amount_cents: 1050, currency: "USD" } }), "create");
    expect(below.message).toBe("The lowest offer we can accept for this product is $10.50.");
    expect(below.field?.name).toBe("amount");
    expect(describeOfferError(http(422, "OFFER_BELOW_MINIMUM", { minimum: "x" }), "create").message).toBe(OFFER_MESSAGES.belowMinimum);
    expect(describeOfferError(http(422, "OFFER_COOLDOWN_ACTIVE", { cooldown_until: "2026-11-19T10:00:00Z" }), "create").message).toMatch(
      /You can make a new offer after/
    );
    expect(describeOfferError(http(422, "OFFER_COOLDOWN_ACTIVE", { cooldown_until: "nope" }), "create").message).toBe(OFFER_MESSAGES.cooldown);
  });

  it("maps above-list-price validation onto the amount field", () => {
    const outcome = describeOfferError(
      http(422, "VALIDATION_ERROR", {}, { errors: [{ loc: ["body", "amount_cents"], msg: "must not exceed", type: "value_error" }] }),
      "answer"
    );
    expect(outcome.field).toEqual({ name: "amount", message: OFFER_MESSAGES.aboveList });
  });

  it("re-reads the offer for every 'it moved on' answer", () => {
    for (const error of [
      http(409, "OFFER_NOT_YOUR_TURN"),
      http(409, "INVALID_STATE_TRANSITION", { offer_status: "accepted" }),
      http(409, "OFFER_AMOUNT_CHANGED", { current_amount: { amount_cents: 1900, currency: "USD" } }),
      http(410, "OFFER_EXPIRED"),
    ]) {
      expect(describeOfferError(error, "answer").refetchOffer).toBe(true);
    }
    expect(describeOfferError(http(409, "OFFER_AMOUNT_CHANGED", { current_amount: { amount_cents: 1900, currency: "USD" } }), "answer").message).toMatch(
      /\$19\.00/
    );
  });

  it("handles csrf, verification, session, rate limit, pause and unknown outcomes", () => {
    expect(describeOfferError({ kind: "csrf", message: "x", raw: undefined }, "create").message).toBe(OFFER_MESSAGES.csrf);
    expect(describeOfferError(http(403, "CSRF_INVALID"), "answer").message).toBe(OFFER_MESSAGES.csrf);
    expect(describeOfferError(http(403, "EMAIL_VERIFICATION_REQUIRED"), "create")).toMatchObject({ kind: "verify-email", refetchAuth: true });
    expect(describeOfferError(http(401, "AUTH_REQUIRED"), "create").kind).toBe("session-expired");
    expect(describeOfferError(http(429, "RATE_LIMITED", {}, { retryAfterSeconds: 120 }), "create").message).toMatch(/2 minutes/);
    expect(describeOfferError(http(503, "ORDERS_PAUSED"), "create").message).toBe(OFFER_MESSAGES.paused);
    expect(describeOfferError({ kind: "timeout", message: "x", raw: undefined }, "create").message).toBe(OFFER_MESSAGES.uncertainCreate);
    expect(describeOfferError({ kind: "network", message: "x", raw: undefined }, "answer")).toMatchObject({
      message: OFFER_MESSAGES.uncertainAnswer,
      refetchOffer: true,
    });
  });
});

describe("describeOfferCheckoutError", () => {
  it("separates uncertain, already-active, unpaid-order and final refusals", () => {
    expect(describeOfferCheckoutError({ kind: "timeout", message: "x", raw: undefined }).kind).toBe("uncertain");
    expect(describeOfferCheckoutError(http(409, "IDEMPOTENCY_REQUEST_IN_PROGRESS")).kind).toBe("uncertain");
    expect(describeOfferCheckoutError(http(500, "INTERNAL_ERROR")).kind).toBe("uncertain");
    expect(describeOfferCheckoutError(http(409, "PAYMENT_ALREADY_ACTIVE", { redirect_url: "https://pay.example/x" }))).toEqual({
      kind: "already-active",
      message: OFFER_CHECKOUT_MESSAGES.alreadyActive,
      resumeUrl: "https://pay.example/x",
    });
    expect(describeOfferCheckoutError(http(409, "PAYMENT_ALREADY_ACTIVE", { redirect_url: "javascript:alert(1)" }))).toMatchObject({
      resumeUrl: null,
      message: OFFER_CHECKOUT_MESSAGES.alreadyActiveProcessing,
    });
    expect(describeOfferCheckoutError(http(502, "PAYMENT_PROVIDER_UNAVAILABLE", { order_id: "o-1", order_number: "B3D-1" }))).toMatchObject({
      kind: "payment-not-started",
      orderId: "o-1",
      orderNumber: "B3D-1",
    });
    expect(describeOfferCheckoutError(http(410, "OFFER_CHECKOUT_EXPIRED"))).toMatchObject({ refetchOffer: true, message: OFFER_CHECKOUT_MESSAGES.windowEnded });
    expect(describeOfferCheckoutError(http(409, "IDEMPOTENCY_KEY_CONFLICT"))).toMatchObject({ retireKey: true });
    expect(describeOfferCheckoutError(http(409, "PRODUCT_ALREADY_OWNED")).kind).toBe("owned");
    expect(describeOfferCheckoutError(http(403, "CSRF_INVALID")).message).toBe(OFFER_CHECKOUT_MESSAGES.csrf);
    expect(describeOfferCheckoutError(http(503, "ONLINE_PAYMENT_UNAVAILABLE")).message).not.toMatch(/cart/i);
  });
});
