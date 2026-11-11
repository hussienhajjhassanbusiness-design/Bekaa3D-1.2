import { test, expect, type Page, type Route } from "@playwright/test";
import { stubEmptyCart } from "./support/stubCart";

// Phase 5I — FVS-028 admin payments + refunds against a deterministic,
// stateful stand-in for backend 2dfb27b (payments/api/admin_payments.py,
// admin_refunds.py; payments/domain/refunds.py). Route interception only:
// no backend on :8000, no media server on :8001.
//
// The fake applies the documented rules: refund create needs CSRF and an
// Idempotency-Key (same key + same body replays the 201; a refusal frees the
// key), per-line balances (422 REFUND_EXCEEDS_AVAILABLE with `available`),
// pending -> settled/failed/voided, failed -> reissued (a new pending one);
// a customer gets 404 from the admin boundary.

type Json = Record<string, unknown>;
const uuid = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const ADMIN_ME = { id: "admin-1", email: "admin@example.com", role: "admin", email_verified: true, email_verified_at: "2025-01-01T00:00:00Z", created_at: "2024-01-01T00:00:00Z" };
const CUSTOMER_ME = { ...ADMIN_ME, id: "c-1", role: "customer" };
const ORDER_ID = uuid(31);
const LINE_ID = uuid(311);
const MOCK_PAY = uuid(41);
const CASH_PAY = uuid(42);
const NOW = "2026-11-12T09:00:00Z";
const usd = (amount_cents: number) => ({ amount_cents, currency: "USD" });

function payment(id: string, overrides: Json = {}): Json {
  return {
    id, order_id: ORDER_ID, order_number: "B3D-PAID0001", provider: "mock", status: "paid", amount_cents: 3600, currency: "USD",
    captured_amount_cents: null, captured_currency: null, provider_payment_id: "mock_abc", initiated_at: "2026-11-10T10:00:00Z",
    verified_at: "2026-11-10T10:01:00Z", failed_at: null, expired_at: null, late_captured_at: null, needs_manual_confirmation: false,
    unprocessed_event_count: 0, ...overrides,
  };
}

interface Fake {
  balance: number;
  refunds: Json[];
  keys: Map<string, { body: string; refund: Json }>;
  writes: { path: string; body: string | null; key: string | null; csrf: string | null; status: number }[];
}

function problem(status: number, code: string, extra: Json = {}) {
  return { status, contentType: "application/problem+json", body: JSON.stringify({ type: "about:blank", title: "RAW", status, detail: "RAW DETAIL", code, errors: [], ...extra }) };
}

function order(fake: Fake): Json {
  return {
    id: ORDER_ID, order_number: "B3D-PAID0001", source: "cart", customer_id: "c-1", customer_email: "rana@example.com",
    status: fake.balance < 3600 ? (fake.balance === 0 ? "refunded" : "partially_refunded") : "completed",
    fulfillment_method: "delivery", payment_method: "online", payment_reached_paid: true, payment_due: false, amount_due: null,
    subtotal: usd(3600), tax: usd(0), total: usd(3600),
    delivery_address: { recipient_name: "Rana", governorate: "beqaa", city: "Zahle", area: null, street: "Main St", landmark_notes: null },
    contact_phone: "+96170123456", delivery_fee_note: "x", customer_note: null, admin_note: null, estimated_dispatch_at: null,
    placed_at: "2026-11-10T10:00:00Z", completed_at: NOW, cancelled_at: null,
    lines: [{ id: LINE_ID, product_id: "p", product_type: "physical", name: "Articulated Dragon", image_url: null, unit_price: usd(1800), quantity: 2, line_total: usd(3600), fulfillment_status: "delivered", fulfilled_at: null, delivered_by: null, cancelled_at: null, cancel_reason: null, offer_id: null, lead_time_days: null, batch_size: null, receipt_confirmed_at: null, problem_reported_at: null, available_actions: [] }],
    payments: [{ id: MOCK_PAY, provider: "mock", status: "paid", amount: usd(3600), initiated_at: "2026-11-10T10:00:00Z", verified_at: NOW, late_captured_at: null, recorded_by: null }],
    status_history: [], refunds: fake.refunds.map((r) => ({ id: r.id, kind: r.kind, status: r.status, owed: r.owed, amount: usd(Number(r.amount_cents)), created_at: r.created_at })),
    chargebacks: [], refund_balance: { lines: [{ order_item_id: LINE_ID, balance_cents: fake.balance }], payment_cents: fake.balance },
  };
}

function refund(id: string, amount: number, overrides: Json = {}): Json {
  return {
    id, order_id: ORDER_ID, order_number: "B3D-PAID0001", customer_id: "c-1", payment_id: MOCK_PAY, payment_provider: "mock", kind: "admin",
    status: "pending", owed: false, amount_cents: amount, currency: "USD", reason: "Damaged", requested_by: "admin-1", approved_by: "admin-1",
    items: [{ order_item_id: LINE_ID, product_name: "Articulated Dragon", amount_cents: amount }], reissue_of_refund_id: null, reissued_by_refund_id: null,
    reissued_at: null, settled_at: null, settled_by: null, settlement_reference: null, settlement_note: null, failed_at: null, failed_by: null,
    failure_reason: null, voided_at: null, voided_by: null, void_reason: null, created_at: NOW, ...overrides,
  };
}

async function install(page: Page, me: Json = ADMIN_ME): Promise<Fake> {
  const fake: Fake = { balance: 3600, refunds: [], keys: new Map(), writes: [] };
  await page.context().addCookies([{ name: "csrf_token", value: "e2e-csrf-value", url: "http://localhost:3000" }]);
  await stubEmptyCart(page);
  await page.route(/\/api\/v1\/me$/, (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify(me) }));
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  const guard = (route: Route, fn: () => Promise<void>) => (me.role !== "admin" ? route.fulfill(problem(404, "NOT_FOUND")) : fn());
  const log = (route: Route, status: number) => {
    const r = route.request();
    fake.writes.push({ path: new URL(r.url()).pathname, body: r.postData(), key: r.headers()["idempotency-key"] ?? null, csrf: r.headers()["x-csrf-token"] ?? null, status });
  };

  await page.route(/\/api\/v1\/admin\/payments(\?.*)?$/, (route) =>
    guard(route, async () => {
      const url = new URL(route.request().url());
      let items = [payment(MOCK_PAY), payment(CASH_PAY, { provider: "cash", provider_payment_id: null, order_number: "B3D-CASH0009" })];
      const provider = url.searchParams.get("provider");
      if (provider) items = items.filter((p) => p.provider === provider);
      await json(route, { items, next_cursor: null });
    })
  );
  await page.route(/\/api\/v1\/admin\/payments\/[^/?]+$/, (route) =>
    guard(route, async () => {
      const id = new URL(route.request().url()).pathname.split("/").pop();
      const p = id === MOCK_PAY ? payment(MOCK_PAY) : id === CASH_PAY ? payment(CASH_PAY, { provider: "cash" }) : null;
      if (!p) return route.fulfill(problem(404, "NOT_FOUND"));
      await json(route, {
        payment: p,
        order: { id: ORDER_ID, order_number: "B3D-PAID0001", status: "completed", total_cents: 3600, currency: "USD", placed_at: "2026-11-10T10:00:00Z", cancelled_at: null, hold_expires_at: null, manual_release_available_at: null },
        events: [], history: [{ action: "payment.verified", actor_user_id: null, created_at: NOW, data: null }],
        available_actions: p.provider === "cash" ? [] : ["reconcile"],
      });
    })
  );
  await page.route(/\/api\/v1\/admin\/payments\/[^/]+\/reconcile$/, (route) =>
    guard(route, async () => {
      if (route.request().headers()["x-csrf-token"] !== "e2e-csrf-value") return log(route, 403), route.fulfill(problem(403, "CSRF_INVALID"));
      log(route, 202);
      await json(route, { payment: payment(MOCK_PAY), reconcile: "queued" }, 202);
    })
  );
  await page.route(/\/api\/v1\/admin\/orders\/[^/?]+$/, (route) => guard(route, () => json(route, order(fake))));
  await page.route(/\/api\/v1\/admin\/orders\/[^/]+\/refunds$/, (route) =>
    guard(route, async () => {
      const req = route.request();
      const key = req.headers()["idempotency-key"] ?? "";
      const raw = req.postData() ?? "";
      if (req.headers()["x-csrf-token"] !== "e2e-csrf-value") return log(route, 403), route.fulfill(problem(403, "CSRF_INVALID"));
      const stored = fake.keys.get(key);
      if (stored) {
        if (stored.body !== raw) return log(route, 409), route.fulfill(problem(409, "IDEMPOTENCY_KEY_CONFLICT"));
        log(route, 201);
        return route.fulfill({ status: 201, contentType: "application/json", headers: { "Idempotent-Replayed": "true" }, body: JSON.stringify(stored.refund) });
      }
      const body = JSON.parse(raw) as { items: { amount_cents: number }[] };
      const total = body.items.reduce((s, i) => s + i.amount_cents, 0);
      if (total > fake.balance) {
        log(route, 422);
        return route.fulfill(problem(422, "REFUND_EXCEEDS_AVAILABLE", { available: { lines: [{ order_item_id: LINE_ID, balance_cents: fake.balance }], payment_cents: fake.balance } }));
      }
      const r = refund(uuid(500 + fake.refunds.length), total);
      fake.refunds.push(r);
      fake.balance -= total;
      fake.keys.set(key, { body: raw, refund: r });
      log(route, 201);
      await json(route, r, 201);
    })
  );
  await page.route(/\/api\/v1\/admin\/refunds(\?.*)?$/, (route) =>
    guard(route, async () => {
      const queue = new URL(route.request().url()).searchParams.get("queue") !== "false";
      await json(route, { items: fake.refunds.filter((r) => !queue || r.status === "pending" || r.owed), next_cursor: null });
    })
  );
  await page.route(/\/api\/v1\/admin\/refunds\/[^/?]+$/, (route) =>
    guard(route, async () => {
      const r = fake.refunds.find((x) => x.id === new URL(route.request().url()).pathname.split("/").pop());
      await (r ? json(route, r) : route.fulfill(problem(404, "NOT_FOUND")));
    })
  );
  await page.route(/\/api\/v1\/admin\/refunds\/[^/]+\/(settle|fail|void|reissue)$/, (route) =>
    guard(route, async () => {
      const parts = new URL(route.request().url()).pathname.split("/");
      const action = parts.pop();
      const r = fake.refunds.find((x) => x.id === parts.pop());
      if (!r) return route.fulfill(problem(404, "NOT_FOUND"));
      if (route.request().headers()["x-csrf-token"] !== "e2e-csrf-value") return log(route, 403), route.fulfill(problem(403, "CSRF_INVALID"));
      const body = route.request().postData() ? (JSON.parse(route.request().postData()!) as Json) : {};
      if (action === "reissue") {
        if (r.status !== "failed") return log(route, 409), route.fulfill(problem(409, "INVALID_STATE_TRANSITION", { reason: "not_failed" }));
        const twin = refund(uuid(600 + fake.refunds.length), Number(r.amount_cents), { reissue_of_refund_id: r.id });
        Object.assign(r, { owed: false, reissued_by_refund_id: twin.id, reissued_at: NOW });
        fake.refunds.push(twin);
        log(route, 201);
        return json(route, twin, 201);
      }
      if (r.status !== "pending") return log(route, 409), route.fulfill(problem(409, "INVALID_STATE_TRANSITION", { reason: r.status === "settled" ? "already_settled" : "not_pending" }));
      if (action === "settle") Object.assign(r, { status: "settled", settled_at: NOW, settlement_reference: body.reference ?? null });
      if (action === "fail") Object.assign(r, { status: "failed", owed: true, failed_at: NOW, failure_reason: body.reason });
      if (action === "void") {
        Object.assign(r, { status: "voided", voided_at: NOW, void_reason: body.reason });
        fake.balance += Number(r.amount_cents);
      }
      log(route, 200);
      await json(route, r);
    })
  );
  return fake;
}

test.describe("Admin payments + refunds (Phase 5I / FVS-028)", () => {
  test("a customer gets the real 404", async ({ page }) => {
    await install(page, CUSTOMER_ME);
    await page.goto("/admin/payments");
    await expect(page.getByText(/404/)).toBeVisible();
  });

  test("payments list: mock and cash records, provider filter, detail with reconcile (cash has none)", async ({ page }) => {
    const fake = await install(page);
    await page.goto("/admin/payments");
    await expect(page.getByRole("link", { name: /^Order B3D-/ })).toHaveText(["Order B3D-PAID0001", "Order B3D-CASH0009"]);
    await page.getByLabel("Provider").selectOption("cash");
    await expect(page.getByRole("link", { name: /^Order B3D-/ })).toHaveText(["Order B3D-CASH0009"]);
    await page.getByRole("link", { name: "Order B3D-CASH0009" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Payment for order");
    await expect(page.getByRole("region", { name: "Payment actions" })).toHaveCount(0);
    await page.goto(`/admin/payments/${MOCK_PAY}`);
    await page.getByRole("button", { name: "Check with provider" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Check with provider" }).click();
    await expect(page.getByText(/Check requested/)).toBeVisible();
    expect(fake.writes.at(-1)).toEqual(expect.objectContaining({ path: `/api/v1/admin/payments/${MOCK_PAY}/reconcile`, status: 202 }));
  });

  test("partial refund from the order: refused over balance, recorded, settled; order shows it", async ({ page }) => {
    const fake = await install(page);
    await page.goto(`/admin/orders/${ORDER_ID}`);
    await page.getByRole("button", { name: "Record a refund" }).click();
    const dialog = page.getByRole("dialog", { name: "Record a refund?" });
    await dialog.getByLabel(/Articulated Dragon/).fill("18");
    await dialog.getByLabel("Reason").fill("One dragon cracked");
    // Meanwhile another admin refunded most of it.
    fake.balance = 1000;
    await dialog.getByRole("button", { name: "Record refund" }).click();
    await expect(dialog.getByRole("alert")).toContainText("more than what's left to refund");
    await expect(dialog.getByLabel(/Articulated Dragon \(up to \$10\.00\)/)).toBeVisible();
    // The form now enforces the server's latest balance ($10) on the client.
    await dialog.getByRole("button", { name: "Record refund" }).click();
    await expect(dialog).toContainText("More than this item's refundable balance.");
    // The other refund was voided; reopening re-reads the order's balances.
    fake.balance = 3600;
    await dialog.getByRole("button", { name: "Back" }).click();
    await page.reload();
    await page.getByRole("button", { name: "Record a refund" }).click();
    await dialog.getByLabel(/Articulated Dragon \(up to \$36\.00\)/).fill("18");
    await dialog.getByLabel("Reason").fill("One dragon cracked");
    await dialog.getByRole("button", { name: "Record refund" }).click();
    await expect(page).toHaveURL(/\/admin\/refunds\//);
    const creates = fake.writes.filter((w) => w.path.endsWith("/refunds"));
    expect(creates.map((w) => w.status)).toEqual([422, 201]);
    expect(creates[1]!.key).toMatch(/^[A-Za-z0-9._:-]{8,255}$/);
    expect(creates[1]!.key).not.toBe(creates[0]!.key); // the refusal retired the first key
    expect(JSON.parse(creates[1]!.body!)).toEqual({ items: [{ order_item_id: LINE_ID, amount_cents: 1800 }], reason: "One dragon cracked" });

    await page.getByRole("button", { name: "Mark settled" }).click();
    await page.getByRole("dialog").getByLabel(/Settlement reference/).fill("DASH-1");
    await page.getByRole("dialog").getByRole("button", { name: "Mark settled" }).click();
    await expect(page.getByRole("heading", { level: 1 }).locator("..")).toContainText("Settled");
    await expect(page.getByRole("region", { name: "Refund actions" })).toHaveCount(0);

    await page.goto(`/admin/orders/${ORDER_ID}`);
    await expect(page.getByRole("heading", { level: 1 }).locator("..")).toContainText("Partially refunded");
    await expect(page.getByRole("region", { name: "Refunds" })).toContainText("Settled");
  });

  test("full refund, then fail -> reissue; queue and history; CSRF refusal is safe", async ({ page }) => {
    const fake = await install(page);
    await page.goto(`/admin/orders/${ORDER_ID}`);
    await page.getByRole("button", { name: "Record a refund" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel(/Articulated Dragon/).fill("36");
    await dialog.getByLabel("Reason").fill("Never arrived");
    await dialog.getByRole("button", { name: "Record refund" }).click();
    await expect(page).toHaveURL(/\/admin\/refunds\//);

    await page.context().addCookies([{ name: "csrf_token", value: "stale", url: "http://localhost:3000" }]);
    await page.getByRole("button", { name: "Mark failed" }).click();
    await page.getByRole("dialog").getByLabel("Reason").fill("Card closed");
    await page.getByRole("dialog").getByRole("button", { name: "Mark failed" }).click();
    await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Unable to verify your session");
    await page.context().addCookies([{ name: "csrf_token", value: "e2e-csrf-value", url: "http://localhost:3000" }]);
    await page.getByRole("dialog").getByRole("button", { name: "Mark failed" }).click();
    await expect(page.getByRole("heading", { level: 1 }).locator("..")).toContainText("Still owed");

    await page.getByRole("button", { name: "Reissue refund" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Reissue refund" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
    expect(fake.writes.at(-1)!.key).toMatch(/^[A-Za-z0-9._:-]{8,255}$/);

    await page.goto("/admin/refunds");
    await expect(page.getByRole("link", { name: /^Order B3D-/ })).toHaveCount(1); // the new pending one
    await page.getByLabel("View").selectOption("history");
    await expect(page.getByRole("link", { name: /^Order B3D-/ })).toHaveCount(2);
    await expect(page.getByRole("main")).toContainText("Failed");
  });

  test("keyboard and mobile: refund dialog reachable and fits", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 740 });
    await install(page);
    await page.goto(`/admin/orders/${ORDER_ID}`);
    const button = page.getByRole("button", { name: "Record a refund" });
    await button.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    await page.keyboard.press("Escape");
    await expect(button).toBeFocused();
  });
});
