import { describe, it, expect } from "vitest";
import { CART_MESSAGES, describeCartWriteError } from "./cartErrors";
import type { ApiError } from "@/lib/api/ApiError";

// Every cart write Problem the backend 2dfb27b can return
// (src/app/ordering/api/cart.py `_translate`, identity CSRF/verification
// dependencies, rate limiter). Branching is on status + code (+ typed
// extension members) only; detail/title/msg are never rendered.

function problem(status: number, code: string, raw: Record<string, unknown> = {}, extra: Partial<ApiError> = {}): ApiError {
  return {
    kind: "http",
    status,
    code,
    detail: "RAW DETAIL",
    title: "RAW TITLE",
    message: "x",
    raw: { status, code, detail: "RAW DETAIL", ...raw },
    ...extra,
  };
}

describe("describeCartWriteError", () => {
  it.each([
    ["unavailable", CART_MESSAGES.unavailable],
    ["whatsapp_only", CART_MESSAGES.whatsappOnly],
    ["not_listed", CART_MESSAGES.notListed],
  ])("PRODUCT_NOT_PURCHASABLE with reason %s", (reason, message) => {
    const result = describeCartWriteError(problem(422, "PRODUCT_NOT_PURCHASABLE", { reason }));
    expect(result).toEqual({ message, refetch: true });
  });

  it("PRODUCT_NOT_PURCHASABLE with an unknown reason still gets safe copy", () => {
    expect(describeCartWriteError(problem(422, "PRODUCT_NOT_PURCHASABLE", { reason: "new" })).message).toBe(
      CART_MESSAGES.notPurchasable
    );
  });

  it("QUANTITY_EXCEEDS_LIMIT names the server's max_quantity", () => {
    const result = describeCartWriteError(problem(422, "QUANTITY_EXCEEDS_LIMIT", { max_quantity: 5, requested: 7 }));
    expect(result.message).toBe("You can have at most 5 of this product in your cart.");
    expect(result.refetch).toBe(true);
  });

  it("QUANTITY_EXCEEDS_LIMIT on a merge mentions what is already in the cart", () => {
    const result = describeCartWriteError(
      problem(422, "QUANTITY_EXCEEDS_LIMIT", { max_quantity: 5, requested: 3, current_quantity: 4 })
    );
    expect(result.message).toBe("You can have at most 5 of this product in your cart. You already have 4.");
  });

  it("QUANTITY_EXCEEDS_LIMIT with max_quantity 1 (an STL) says only one copy fits", () => {
    const result = describeCartWriteError(problem(422, "QUANTITY_EXCEEDS_LIMIT", { max_quantity: 1, current_quantity: 1 }));
    expect(result.message).toBe(CART_MESSAGES.singleCopy);
  });

  it("QUANTITY_EXCEEDS_LIMIT without a usable max_quantity falls back to generic limit copy", () => {
    expect(describeCartWriteError(problem(422, "QUANTITY_EXCEEDS_LIMIT", { max_quantity: "5" })).message).toBe(
      CART_MESSAGES.quantityLimit
    );
  });

  it("CART_LINE_LIMIT_REACHED names the server's limit", () => {
    expect(describeCartWriteError(problem(422, "CART_LINE_LIMIT_REACHED", { limit: 50 })).message).toBe(
      "Your cart can hold up to 50 different products. Remove one to add another."
    );
  });

  it("PRODUCT_ALREADY_OWNED", () => {
    expect(describeCartWriteError(problem(409, "PRODUCT_ALREADY_OWNED", { product_ids: ["p"] })).message).toBe(
      CART_MESSAGES.alreadyOwned
    );
  });

  it("404 NOT_FOUND on a line: refetch so the stale line disappears", () => {
    expect(describeCartWriteError(problem(404, "NOT_FOUND"))).toEqual({ message: CART_MESSAGES.lineGone, refetch: true });
  });

  it("EMAIL_VERIFICATION_REQUIRED", () => {
    expect(describeCartWriteError(problem(403, "EMAIL_VERIFICATION_REQUIRED")).message).toBe(CART_MESSAGES.verifyEmail);
  });

  it("CSRF_INVALID from the server and a local missing-cookie csrf error", () => {
    expect(describeCartWriteError(problem(403, "CSRF_INVALID")).message).toBe(CART_MESSAGES.csrf);
    expect(describeCartWriteError({ kind: "csrf", message: "x", raw: null }).message).toBe(CART_MESSAGES.csrf);
  });

  it("401 AUTH_REQUIRED after a failed refresh", () => {
    expect(describeCartWriteError(problem(401, "AUTH_REQUIRED")).message).toBe(CART_MESSAGES.authRequired);
  });

  it("429 RATE_LIMITED with and without Retry-After", () => {
    expect(describeCartWriteError(problem(429, "RATE_LIMITED", {}, { retryAfterSeconds: 120 })).message).toBe(
      "Too many cart changes. Try again in 2 minutes."
    );
    expect(describeCartWriteError(problem(429, "RATE_LIMITED")).message).toBe(CART_MESSAGES.rateLimited);
  });

  it("422 VALIDATION_ERROR on quantity", () => {
    const error = problem(422, "VALIDATION_ERROR", {}, {
      errors: [{ loc: ["body", "quantity"], msg: "raw msg", type: "greater_than_equal" }],
    });
    expect(describeCartWriteError(error)).toEqual({ message: CART_MESSAGES.invalidQuantity, refetch: false });
  });

  it("anything else (network, 500, unknown code) is generic copy, never the server text", () => {
    for (const error of [
      { kind: "network" as const, message: "x", raw: null },
      problem(500, "INTERNAL_ERROR"),
      problem(422, "SOMETHING_NEW"),
      new Error("boom"),
      undefined,
    ]) {
      const result = describeCartWriteError(error);
      expect(result.message).toBe(CART_MESSAGES.generic);
      expect(result.message).not.toContain("RAW");
    }
  });
});
