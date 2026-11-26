import { test, expect, type Page, type Request } from "@playwright/test";
import { stubEmptyCart } from "./support/stubCart";
import { E2E_ORIGIN } from "./support/origin";

// Phase 5F — FVS-027 payment result + payment retry on /account/orders/[id]
// against a deterministic, in-memory stand-in for backend 2dfb27b:
//   GET  /api/v1/me/orders/{id}           (OrderDetailRead: the payment truth)
//   POST /api/v1/me/orders/{id}/payments  (PaymentRetryRead / Problems)
// Route interception only: no backend on :8000, no media server on :8001.
//
// The fake applies the documented retry rules (ordering/api/payment_retry.py,
// docs/payment-recovery.md): X-CSRF-Token must match the cookie; the
// Idempotency-Key header is required and matches the backend pattern; the
// same key replays the stored 201 (`Idempotent-Replayed: true`); the body
// must be exactly `{}` from this frontend. The mock provider's redirect_url
// is {FRONTEND}/checkout/return?order=<number>.
//
// Route patterns are exact: `/api/v1/me`, `/api/v1/settings/public`,
// `/api/v1/me/orders/{id}`, `/api/v1/me/orders/{id}/payments`.

const CSRF = "e2e-csrf-value";
const KEY_PATTERN = /^[A-Za-z0-9._:-]{8,255}$/;

const ME = {
  id: "u-1",
  email: "ada@example.com",
  role: "customer",
  email_verified: true,
  email_verified_at: "2025-01-01T00:00:00Z",
  created_at: "2024-01-01T00:00:00Z",
};

const SETTINGS = {
  accepting_orders: true,
  cash_payment_enabled: true,
  cash_max_order_total: { amount_cents: 10000, currency: "USD" },
  pickup_address: "Bekaa3D workshop, Zahle",
  pickup_hours: "Mon-Fri 10:00-18:00",
  whatsapp_number: null,
};

type Json = Record<string, unknown>;
const usd = (amount_cents: number) => ({ amount_cents, currency: "USD" });
const ORDER_ID = "00000000-0000-4000-8000-000000000101";
const NUMBER = "B3D-2026-000101";
const RETURN_URL = `${E2E_ORIGIN}/checkout/return?order=${NUMBER}`;

function minutesFromNow(minutes: number): string {
  return new Date(Date.now() + minutes * 60_000).toISOString();
}

function onlineOrder(overrides: Json = {}): Json {
  return {
    id: ORDER_ID,
    order_number: NUMBER,
    source: "cart",
    status: "pending_payment",
    fulfillment_method: "pickup",
    payment_method: "online",
    payment_due: false,
    amount_due: null,
    can_cancel: false,
    can_retry_payment: false,
    hold_expires_at: minutesFromNow(25),
    subtotal: usd(3600),
    tax: usd(0),
    total: usd(3600),
    delivery_address: null,
    contact_phone: "+96171999888",
    delivery_fee_note: null,
    estimated_dispatch_at: null,
    placed_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    completed_at: null,
    cancelled_at: null,
    customer_note: null,
    lines: [
      {
        id: "l-1",
        product_id: "p-1",
        product_type: "physical",
        name: "Articulated Dragon",
        image_url: null,
        unit_price: usd(1800),
        quantity: 2,
        line_total: usd(3600),
        fulfillment_status: "pending",
        fulfilled_at: null,
        cancelled_at: null,
        receipt_confirmed_at: null,
        problem_reported_at: null,
      },
    ],
    payment: { status: "pending", provider: "mock", amount: usd(3600) },
    status_history: [{ order_item_id: null, from_status: null, to_status: "pending_payment", at: "2026-11-10T10:30:00Z" }],
    refunds: [],
    ...overrides,
  };
}

const failedRetryable = (overrides: Json = {}) =>
  onlineOrder({ payment: { status: "failed", provider: "mock", amount: usd(3600) }, can_retry_payment: true, ...overrides });

function problem(status: number, code: string, extra: Json = {}, headers: Record<string, string> = {}) {
  return {
    status,
    contentType: "application/problem+json",
    headers,
    body: JSON.stringify({ type: "about:blank", title: "RAW TITLE", status, detail: "RAW DETAIL", code, errors: [], ...extra }),
  };
}

interface RetryCall {
  key: string | undefined;
  csrf: string | undefined;
  body: unknown;
}

type RetryAnswer = "created" | "abort" | { problem: ReturnType<typeof problem> };

interface Fake {
  detailCalls: number;
  retryCalls: RetryCall[];
  // Swapped by tests to simulate the server-side lifecycle.
  order: Json;
  // Applied to each detail read before answering (e.g. become paid after N reads).
  onDetail?: (fake: Fake) => void;
  retryAnswers: RetryAnswer[];
}

async function installFake(page: Page, order: Json): Promise<Fake> {
  const fake: Fake = { detailCalls: 0, retryCalls: [], order, retryAnswers: [] };
  const stored = new Map<string, Json>();

  await page.context().addCookies([{ name: "csrf_token", value: CSRF, url: E2E_ORIGIN }]);
  await stubEmptyCart(page);
  await page.route(/\/api\/v1\/me$/, (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(ME) }));
  await page.route(/\/api\/v1\/settings\/public$/, (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(SETTINGS) })
  );
  await page.route(/\/api\/v1\/me\/orders\/[^/?]+$/, (route) => {
    fake.detailCalls += 1;
    fake.onDetail?.(fake);
    return route.fulfill({ contentType: "application/json", body: JSON.stringify(fake.order) });
  });
  await page.route(/\/api\/v1\/me\/orders\/[^/?]+\/payments$/, async (route) => {
    const request: Request = route.request();
    if (request.method() !== "POST") return route.fallback();
    const headers = request.headers();
    const call: RetryCall = { key: headers["idempotency-key"], csrf: headers["x-csrf-token"], body: request.postDataJSON() };
    fake.retryCalls.push(call);
    if (call.csrf !== CSRF) return route.fulfill(problem(403, "CSRF_INVALID"));
    if (!call.key || !KEY_PATTERN.test(call.key)) return route.fulfill(problem(422, "VALIDATION_ERROR"));
    const replay = stored.get(call.key);
    if (replay) {
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        headers: { "Idempotent-Replayed": "true" },
        body: JSON.stringify(replay),
      });
    }
    const answer = fake.retryAnswers.shift() ?? "created";
    const created = {
      order: { id: ORDER_ID, order_number: NUMBER, status: "pending_payment", total_cents: 3600, currency: "USD", hold_expires_at: minutesFromNow(30) },
      payment: { id: "pay-2", status: "pending", provider: "mock", amount_cents: 3600, currency: "USD", redirect_url: RETURN_URL },
    };
    if (answer === "abort") {
      // The server committed the attempt, but the response never arrived.
      stored.set(call.key, created);
      return route.abort("failed");
    }
    if (answer !== "created") return route.fulfill(answer.problem);
    stored.set(call.key, created);
    fake.order = onlineOrder({ can_retry_payment: false, hold_expires_at: created.order.hold_expires_at });
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(created) });
  });
  return fake;
}

const paymentRegion = (page: Page) => page.getByRole("region", { name: "Payment" });

async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

test.describe("Payment result and retry (Phase 5F / FVS-027)", () => {
  test("a pending online payment is re-checked and shows Paid once the server says so, then polling stops", async ({ page }) => {
    const fake = await installFake(page, onlineOrder());
    fake.onDetail = (f) => {
      if (f.detailCalls >= 3) {
        f.order = onlineOrder({
          status: "in_progress",
          hold_expires_at: null,
          payment: { status: "paid", provider: "mock", amount: usd(3600) },
        });
      }
    };
    await page.goto(`/account/orders/${ORDER_ID}`);
    const payment = paymentRegion(page);
    await expect(payment.getByText("Awaiting payment")).toBeVisible();
    await expect(payment.getByRole("status")).toContainText("Checking for a payment update");
    await expect(payment).toContainText("Time left to complete payment");
    await expect(payment.getByText("Paid", { exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(payment).toContainText("Your payment has been confirmed.");
    await expect(payment.getByRole("status")).toHaveCount(0);
    const settled = fake.detailCalls;
    await page.waitForTimeout(4_000);
    expect(fake.detailCalls).toBe(settled);
  });

  test("processing reads as processing, never paid", async ({ page }) => {
    await installFake(page, onlineOrder({ payment: { status: "processing", provider: "mock", amount: usd(3600) } }));
    await page.goto(`/account/orders/${ORDER_ID}`);
    const payment = paymentRegion(page);
    await expect(payment.getByText("Payment processing")).toBeVisible();
    await expect(payment).toContainText("being processed");
    await expect(page.getByText("Paid", { exact: true })).toHaveCount(0);
    await expect(payment.getByRole("button", { name: /retry payment/i })).toHaveCount(0);
  });

  test("failed payment: Retry payment posts {} with CSRF and an Idempotency-Key, then follows the server's redirect to a neutral return page", async ({ page }) => {
    const fake = await installFake(page, failedRetryable());
    await page.goto(`/account/orders/${ORDER_ID}`);
    const payment = paymentRegion(page);
    await expect(payment.getByText("Payment failed")).toBeVisible();
    await expect(payment).toContainText("Your last payment attempt didn't go through.");
    await payment.getByRole("button", { name: "Retry payment" }).click();
    await expect(page).toHaveURL(`/checkout/return?order=${NUMBER}`);
    expect(fake.retryCalls).toHaveLength(1);
    expect(fake.retryCalls[0]!.body).toEqual({});
    expect(fake.retryCalls[0]!.csrf).toBe(CSRF);
    expect(fake.retryCalls[0]!.key).toMatch(KEY_PATTERN);

    // The header can also hold a "Loading…" status region: match the page's own.
    const returnStatus = page.getByRole("status").filter({ hasText: "confirmed yet" });
    await expect(returnStatus).toContainText("Your payment hasn't been confirmed yet.");
    await expect(returnStatus).toContainText("Check your orders for the latest status.");
    const text = (await page.locator("body").textContent()) ?? "";
    expect(text).not.toMatch(/payment (was )?successful|payment (has )?failed|order is paid|has been paid/i);
    await page.getByRole("link", { name: "View your orders" }).click();
    await expect(page).toHaveURL(/\/account\/orders$/);
  });

  test("an uncertain retry is resent with the SAME key and replays; a later definitive failure gets a NEW key", async ({ page }) => {
    const fake = await installFake(page, failedRetryable());
    fake.retryAnswers = ["abort"];
    await page.goto(`/account/orders/${ORDER_ID}`);
    const payment = paymentRegion(page);
    await payment.getByRole("button", { name: "Retry payment" }).click();
    await expect(payment.getByRole("alert")).toContainText("We couldn't confirm whether your payment was started");
    await expect(page.getByText("RAW DETAIL")).toHaveCount(0);
    await payment.getByRole("button", { name: "Try again" }).click();
    await expect(page).toHaveURL(`/checkout/return?order=${NUMBER}`);
    expect(fake.retryCalls).toHaveLength(2);
    expect(fake.retryCalls[1]!.key).toBe(fake.retryCalls[0]!.key);
  });

  test("a provider failure (502) is final for that key: the next press starts a new attempt", async ({ page }) => {
    const fake = await installFake(page, failedRetryable());
    fake.retryAnswers = [{ problem: problem(502, "PAYMENT_PROVIDER_UNAVAILABLE", { order_id: ORDER_ID, order_number: NUMBER }) }];
    await page.goto(`/account/orders/${ORDER_ID}`);
    const payment = paymentRegion(page);
    await payment.getByRole("button", { name: "Retry payment" }).click();
    await expect(payment.getByRole("alert")).toContainText("Your payment couldn't be started, so nothing has been charged.");
    await payment.getByRole("button", { name: "Retry payment" }).click();
    await expect(page).toHaveURL(`/checkout/return?order=${NUMBER}`);
    expect(fake.retryCalls).toHaveLength(2);
    expect(fake.retryCalls[1]!.key).not.toBe(fake.retryCalls[0]!.key);
  });

  test("a double click sends one retry", async ({ page }) => {
    const fake = await installFake(page, failedRetryable());
    await page.goto(`/account/orders/${ORDER_ID}`);
    await paymentRegion(page).getByRole("button", { name: "Retry payment" }).dblclick();
    await expect(page).toHaveURL(`/checkout/return?order=${NUMBER}`);
    expect(fake.retryCalls).toHaveLength(1);
  });

  test("PAYMENT_ALREADY_ACTIVE offers Continue to payment with the live attempt's URL", async ({ page }) => {
    const fake = await installFake(page, failedRetryable());
    fake.retryAnswers = [
      { problem: problem(409, "PAYMENT_ALREADY_ACTIVE", { payment_id: "p-1", payment_status: "pending", redirect_url: RETURN_URL }) },
    ];
    await page.goto(`/account/orders/${ORDER_ID}`);
    const payment = paymentRegion(page);
    await payment.getByRole("button", { name: "Retry payment" }).click();
    await expect(payment.getByRole("alert")).toContainText("A payment for this order is already in progress.");
    await expect(page).toHaveURL(new RegExp(`/account/orders/${ORDER_ID}$`));
    await payment.getByRole("button", { name: "Continue to payment" }).click();
    await expect(page).toHaveURL(`/checkout/return?order=${NUMBER}`);
  });

  test("a refused retry (hold expired) explains why and the re-read order drops the button", async ({ page }) => {
    const fake = await installFake(page, failedRetryable());
    fake.retryAnswers = [{ problem: problem(409, "INVALID_STATE_TRANSITION", { reason: "checkout_hold_expired" }) }];
    const reads = fake.detailCalls;
    await page.goto(`/account/orders/${ORDER_ID}`);
    const payment = paymentRegion(page);
    await expect(payment.getByRole("button", { name: "Retry payment" })).toBeVisible();
    fake.order = failedRetryable({ can_retry_payment: false });
    await payment.getByRole("button", { name: "Retry payment" }).click();
    await expect(payment.getByRole("alert")).toContainText("The time to pay for this order has ended");
    await expect(payment.getByRole("button", { name: "Retry payment" })).toHaveCount(0);
    expect(fake.detailCalls).toBeGreaterThan(reads + 1);
    await expect(page.getByText(/RAW/)).toHaveCount(0);
  });

  test("CSRF failure shows safe copy and no redirect", async ({ page }) => {
    const fake = await installFake(page, failedRetryable());
    fake.retryAnswers = [{ problem: problem(403, "CSRF_INVALID") }];
    await page.goto(`/account/orders/${ORDER_ID}`);
    const payment = paymentRegion(page);
    await payment.getByRole("button", { name: "Retry payment" }).click();
    await expect(payment.getByRole("alert")).toContainText("Unable to verify your session.");
    await expect(page).toHaveURL(new RegExp(`/account/orders/${ORDER_ID}$`));
  });

  test("cash order: no retry, no countdown, no polling", async ({ page }) => {
    const fake = await installFake(
      page,
      onlineOrder({
        payment_method: "cash",
        status: "in_progress",
        fulfillment_method: "delivery",
        payment_due: true,
        amount_due: usd(3600),
        hold_expires_at: null,
        payment: null,
        can_retry_payment: false,
        delivery_address: { recipient_name: "Ada", governorate: "beqaa", city: "Zahle", area: null, street: "Main St", landmark_notes: null },
      })
    );
    await page.goto(`/account/orders/${ORDER_ID}`);
    const payment = paymentRegion(page);
    await expect(payment).toContainText("Payment due in cash to the courier on delivery: $36.00");
    await expect(payment.getByRole("button")).toHaveCount(0);
    await expect(payment).not.toContainText(/time left|checking/i);
    await page.waitForTimeout(4_000);
    expect(fake.detailCalls).toBe(1);
    expect(fake.retryCalls).toHaveLength(0);
  });

  test("hold countdown reaching zero re-reads the order and claims no expiry", async ({ page }) => {
    // A failed attempt is not transient, so the only re-read is the countdown's.
    const failed = { status: "failed", provider: "mock", amount: usd(3600) };
    const fake = await installFake(page, onlineOrder({ payment: failed }));
    // The server's deadline is 6 s after the page's first read, whatever the compile time.
    fake.onDetail = (f) => {
      if (f.detailCalls === 1) f.order = onlineOrder({ payment: failed, hold_expires_at: new Date(Date.now() + 6_000).toISOString() });
    };
    await page.goto(`/account/orders/${ORDER_ID}`);
    const payment = paymentRegion(page);
    await expect(payment).toContainText("Time left to complete payment");
    expect(fake.detailCalls).toBe(1);
    await expect(payment).toContainText("The time to complete payment is up.", { timeout: 15_000 });
    await expect.poll(() => fake.detailCalls).toBe(2);
    await expect(payment).toContainText("may be released");
    await expect(payment).not.toContainText(/was released|has expired|order expired/i);
    await expect(page.getByRole("heading", { level: 1 }).locator("..")).not.toContainText("Cancelled");
  });

  test("refunded and partially refunded payments are presented without refund actions", async ({ page }) => {
    const fake = await installFake(
      page,
      onlineOrder({ status: "refunded", hold_expires_at: null, payment: { status: "refunded", provider: "mock", amount: usd(3600) } })
    );
    await page.goto(`/account/orders/${ORDER_ID}`);
    await expect(paymentRegion(page).getByText("Refunded", { exact: true })).toBeVisible();
    await expect(paymentRegion(page)).toContainText("This payment has been refunded.");
    await expect(page.getByRole("button", { name: /refund/i })).toHaveCount(0);

    fake.order = onlineOrder({
      status: "partially_refunded",
      hold_expires_at: null,
      payment: { status: "partially_refunded", provider: "mock", amount: usd(3600) },
      refunds: [{ kind: "admin", status: "refunded", amount: usd(1800), created_at: "2026-11-11T12:00:00Z" }],
    });
    await page.reload();
    await expect(paymentRegion(page).getByText("Partially refunded", { exact: true })).toBeVisible();
    await expect(paymentRegion(page)).toContainText("Part of this payment has been refunded.");
    await expect(page.getByRole("region", { name: "Refunds" })).toContainText("$18.00");
  });

  test("an unknown payment status shows 'Status unavailable', never the raw value", async ({ page }) => {
    await installFake(page, onlineOrder({ payment: { status: "held_for_review", provider: "mock", amount: usd(3600) } }));
    await page.goto(`/account/orders/${ORDER_ID}`);
    await expect(paymentRegion(page).getByText("Status unavailable")).toBeVisible();
    await expect(page.getByText(/held_for_review/)).toHaveCount(0);
  });

  test("the return page makes no claim even with provider-looking parameters", async ({ page }) => {
    await installFake(page, onlineOrder());
    await page.goto(`/checkout/return?order=${NUMBER}&status=success&paid=true`);
    await expect(page.getByRole("status").filter({ hasText: "confirmed yet" })).toContainText(
      "Your payment hasn't been confirmed yet."
    );
    const text = (await page.locator("body").textContent()) ?? "";
    expect(text).not.toMatch(/payment (was )?successful|order is paid|has been paid|payment (has )?failed/i);
    await expect(page.getByRole("link", { name: "View your orders" })).toHaveAttribute("href", "/account/orders");
  });

  test("mobile width: a failed order with Retry payment has no horizontal scroll", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await installFake(page, failedRetryable());
    await page.goto(`/account/orders/${ORDER_ID}`);
    await expect(paymentRegion(page).getByRole("button", { name: "Retry payment" })).toBeVisible();
    await noHorizontalScroll(page);
  });

  test("keyboard only: reach Retry payment and start it with Enter", async ({ page }) => {
    const fake = await installFake(page, failedRetryable());
    await page.goto(`/account/orders/${ORDER_ID}`);
    const button = paymentRegion(page).getByRole("button", { name: "Retry payment" });
    await expect(button).toBeVisible();
    for (let i = 0; i < 60; i += 1) {
      await page.keyboard.press("Tab");
      if (await button.evaluate((el) => el === document.activeElement)) break;
    }
    await expect(button).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(`/checkout/return?order=${NUMBER}`);
    expect(fake.retryCalls).toHaveLength(1);
  });
});
