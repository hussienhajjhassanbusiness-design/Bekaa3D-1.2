import { describe, expect, it } from "vitest";
import type { ApiError } from "@/lib/api/ApiError";
import { describePaymentRetryError, PAYMENT_RETRY_MESSAGES } from "./paymentRetryErrors";

// Every POST /me/orders/{id}/payments failure (backend 2dfb27b
// ordering/api/payment_retry.py _RESPONSES) branches on status + code +
// typed extensions only; title/detail are never returned.

function http(status: number, code: string, extra: Record<string, unknown> = {}, more: Partial<ApiError> = {}): ApiError {
  return {
    kind: "http",
    status,
    code,
    title: "RAW TITLE",
    detail: "RAW DETAIL",
    message: "RAW MESSAGE",
    raw: { status, code, title: "RAW TITLE", detail: "RAW DETAIL", errors: [], ...extra },
    ...more,
  };
}

function noRawText(outcome: { message: string }) {
  expect(outcome.message).not.toMatch(/RAW/);
}

describe("describePaymentRetryError", () => {
  it.each([
    ["network", { kind: "network", message: "RAW", raw: undefined } as ApiError],
    ["timeout", { kind: "timeout", message: "RAW", raw: undefined } as ApiError],
    ["parse", { kind: "parse", message: "RAW", raw: undefined } as ApiError],
    ["500", http(500, "INTERNAL_ERROR")],
  ])("%s is uncertain: keep the key, resend the same attempt", (_label, error) => {
    const outcome = describePaymentRetryError(error);
    expect(outcome.uncertain).toBe(true);
    expect(outcome.message).toBe(PAYMENT_RETRY_MESSAGES.uncertain);
    noRawText(outcome);
  });

  it("IDEMPOTENCY_REQUEST_IN_PROGRESS is uncertain with its own copy", () => {
    const outcome = describePaymentRetryError(http(409, "IDEMPOTENCY_REQUEST_IN_PROGRESS", { order_id: "o" }));
    expect(outcome.uncertain).toBe(true);
    expect(outcome.message).toBe(PAYMENT_RETRY_MESSAGES.inProgress);
  });

  it("PAYMENT_ALREADY_ACTIVE with a pending attempt's redirect_url offers to resume it exactly", () => {
    const url = "https://pay.example.test/session/abc?x=1";
    const outcome = describePaymentRetryError(
      http(409, "PAYMENT_ALREADY_ACTIVE", { payment_id: "p", payment_status: "pending", redirect_url: url })
    );
    expect(outcome.kind).toBe("already-active");
    expect(outcome.resumeUrl).toBe(url);
    expect(outcome.uncertain).toBe(false);
    expect(outcome.refetchOrder).toBe(true);
    expect(outcome.message).toBe(PAYMENT_RETRY_MESSAGES.alreadyActiveResume);
  });

  it("PAYMENT_ALREADY_ACTIVE while processing (redirect_url null) has nothing to resume", () => {
    const outcome = describePaymentRetryError(
      http(409, "PAYMENT_ALREADY_ACTIVE", { payment_id: "p", payment_status: "processing", redirect_url: null })
    );
    expect(outcome.kind).toBe("already-active");
    expect(outcome.resumeUrl).toBeNull();
    expect(outcome.message).toBe(PAYMENT_RETRY_MESSAGES.alreadyActiveProcessing);
  });

  it.each(["javascript:alert(1)", "data:text/html,x", "/relative/path", 42])(
    "PAYMENT_ALREADY_ACTIVE never offers an unsafe or malformed redirect (%s)",
    (redirect) => {
      const outcome = describePaymentRetryError(
        http(409, "PAYMENT_ALREADY_ACTIVE", { payment_status: "pending", redirect_url: redirect })
      );
      expect(outcome.resumeUrl).toBeNull();
    }
  );

  it.each([
    ["cash_order", PAYMENT_RETRY_MESSAGES.cashOrder],
    ["order_cancelled", PAYMENT_RETRY_MESSAGES.orderCancelled],
    ["order_not_payable", PAYMENT_RETRY_MESSAGES.notPayable],
    ["checkout_hold_expired", PAYMENT_RETRY_MESSAGES.holdExpired],
    ["offer_checkout_expired", PAYMENT_RETRY_MESSAGES.offerExpired],
    ["some_future_reason", PAYMENT_RETRY_MESSAGES.notPayable],
    ["toString", PAYMENT_RETRY_MESSAGES.notPayable],
  ])("INVALID_STATE_TRANSITION reason %s is a final refusal that refetches the order", (reason, message) => {
    const outcome = describePaymentRetryError(http(409, "INVALID_STATE_TRANSITION", { reason }));
    expect(outcome.kind).toBe("not-retryable");
    expect(outcome.message).toBe(message);
    expect(outcome.uncertain).toBe(false);
    expect(outcome.refetchOrder).toBe(true);
  });

  it("502 PAYMENT_PROVIDER_UNAVAILABLE is definitive: nothing charged, a new press is a new attempt", () => {
    const outcome = describePaymentRetryError(http(502, "PAYMENT_PROVIDER_UNAVAILABLE", { order_id: "o" }));
    expect(outcome.kind).toBe("provider-unavailable");
    expect(outcome.uncertain).toBe(false);
    expect(outcome.refetchOrder).toBe(true);
    expect(outcome.message).toBe(PAYMENT_RETRY_MESSAGES.providerUnavailable);
  });

  it.each([
    [http(409, "IDEMPOTENCY_KEY_CONFLICT"), PAYMENT_RETRY_MESSAGES.keyConflict],
    [http(422, "PAYMENT_METHOD_NOT_ALLOWED", { reason: "provider_not_configured" }), PAYMENT_RETRY_MESSAGES.onlineUnavailable],
    [http(422, "PAYMENT_METHOD_NOT_ALLOWED", { reason: "provider_required" }), PAYMENT_RETRY_MESSAGES.onlineUnavailable],
    [http(422, "PAYMENT_METHOD_NOT_ALLOWED", { reason: "other" }), PAYMENT_RETRY_MESSAGES.methodNotAllowed],
    [http(422, "VALIDATION_ERROR"), PAYMENT_RETRY_MESSAGES.generic],
    [http(503, "ONLINE_PAYMENT_UNAVAILABLE"), PAYMENT_RETRY_MESSAGES.onlineUnavailable],
    [http(403, "CSRF_INVALID"), PAYMENT_RETRY_MESSAGES.csrf],
    [{ kind: "csrf", message: "RAW", raw: undefined } as ApiError, PAYMENT_RETRY_MESSAGES.csrf],
    [http(403, "EMAIL_VERIFICATION_REQUIRED"), PAYMENT_RETRY_MESSAGES.verifyEmail],
    [http(401, "AUTH_REQUIRED"), PAYMENT_RETRY_MESSAGES.sessionExpired],
    [http(404, "NOT_FOUND"), PAYMENT_RETRY_MESSAGES.notFound],
    [http(429, "RATE_LIMITED"), PAYMENT_RETRY_MESSAGES.rateLimited],
    [http(418, "SOMETHING_NEW"), PAYMENT_RETRY_MESSAGES.generic],
  ])("definitive answer %#", (error, message) => {
    const outcome = describePaymentRetryError(error);
    expect(outcome.message).toBe(message);
    expect(outcome.uncertain).toBe(false);
    noRawText(outcome);
  });

  it("429 names the Retry-After wait when given", () => {
    const outcome = describePaymentRetryError(http(429, "RATE_LIMITED", {}, { retryAfterSeconds: 1800 }));
    expect(outcome.message).toBe("Too many payment attempts. Please try again in 30 minutes.");
  });

  it("session expiry and email verification carry their own kinds", () => {
    expect(describePaymentRetryError(http(401, "AUTH_REQUIRED")).kind).toBe("session-expired");
    expect(describePaymentRetryError(http(403, "EMAIL_VERIFICATION_REQUIRED")).kind).toBe("verify-email");
  });

  it("a non-ApiError (thrown before sending) is a generic, definitive failure", () => {
    const outcome = describePaymentRetryError(new Error("boom"));
    expect(outcome.uncertain).toBe(false);
    expect(outcome.message).toBe(PAYMENT_RETRY_MESSAGES.generic);
  });
});
