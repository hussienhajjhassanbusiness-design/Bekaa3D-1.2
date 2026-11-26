import { test, expect, type Page, type Route } from "@playwright/test";
import { stubEmptyCart } from "./support/stubCart";
import { E2E_ORIGIN } from "./support/origin";

// Phase 6A — admin operations completion against a deterministic stand-in
// for backend 2dfb27b: cash blocks (ordering/api/admin_cash_blocks.py),
// manual release (ordering/api/admin_release.py), chargeback create
// (payments/api/admin_chargebacks.py). Route interception only: no backend
// on :8000, no media server on :8001. Exact route patterns.

type Json = Record<string, unknown>;
const uuid = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const ADMIN_ME = { id: "admin-1", email: "admin@example.com", role: "admin", email_verified: true, email_verified_at: "2025-01-01T00:00:00Z", created_at: "2024-01-01T00:00:00Z" };
const ORDER_ID = uuid(71);
const LINE_ID = uuid(711);
const PAY_ID = uuid(72);
const UNPAID_ORDER = uuid(73);
const UNPAID_PAY = uuid(74);
const usd = (amount_cents: number) => ({ amount_cents, currency: "USD" });

function problem(status: number, code: string, extra: Json = {}) {
  return { status, contentType: "application/problem+json", body: JSON.stringify({ type: "about:blank", title: "RAW", status, detail: "RAW DETAIL", code, errors: [], ...extra }) };
}

interface Fake {
  blocks: Json[];
  chargebacks: Json[];
  writes: { path: string; body: string | null; key: string | null; csrf: string | null }[];
  phoneInUrl: boolean;
}

function order(fake: Fake): Json {
  return {
    id: ORDER_ID, order_number: "B3D-DISP0001", source: "cart", customer_id: "c-1", customer_email: "rana@example.com",
    status: "completed", fulfillment_method: "delivery", payment_method: "online", payment_reached_paid: true, payment_due: false, amount_due: null,
    subtotal: usd(3600), tax: usd(0), total: usd(3600), delivery_address: null, contact_phone: null, delivery_fee_note: null,
    customer_note: null, admin_note: null, estimated_dispatch_at: null, placed_at: "2026-11-10T10:00:00Z", completed_at: null, cancelled_at: null,
    lines: [{ id: LINE_ID, product_id: "p", product_type: "physical", name: "Articulated Dragon", image_url: null, unit_price: usd(1800), quantity: 2, line_total: usd(3600), fulfillment_status: "delivered", fulfilled_at: null, delivered_by: null, cancelled_at: null, cancel_reason: null, offer_id: null, lead_time_days: null, batch_size: null, receipt_confirmed_at: null, problem_reported_at: null, available_actions: [] }],
    payments: [{ id: PAY_ID, provider: "mock", status: "paid", amount: usd(3600), initiated_at: "2026-11-10T10:00:00Z", verified_at: null, late_captured_at: null, recorded_by: null }],
    status_history: [], refunds: [], chargebacks: fake.chargebacks, refund_balance: { lines: [{ order_item_id: LINE_ID, balance_cents: 3600 }], payment_cents: 3600 },
  };
}

async function install(page: Page): Promise<Fake> {
  const fake: Fake = {
    blocks: [
      { id: "b-1", customer_id: "c-1", order_id: uuid(81), order_number: "B3D-REFU0001", reason: "refused", created_at: "2026-11-09T10:00:00Z", active: true, cleared_at: null, cleared_by: null },
      { id: "b-2", customer_id: "c-2", order_id: uuid(82), order_number: "B3D-NOSH0002", reason: "no_show", created_at: "2026-11-08T10:00:00Z", active: true, cleared_at: null, cleared_by: null },
    ],
    chargebacks: [],
    writes: [],
    phoneInUrl: false,
  };
  await page.context().addCookies([{ name: "csrf_token", value: "e2e-csrf-value", url: E2E_ORIGIN }]);
  await stubEmptyCart(page);
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  const log = (route: Route) => {
    const r = route.request();
    fake.writes.push({ path: new URL(r.url()).pathname, body: r.postData(), key: r.headers()["idempotency-key"] ?? null, csrf: r.headers()["x-csrf-token"] ?? null });
  };
  await page.route(/\/api\/v1\/me$/, (r) => json(r, ADMIN_ME));
  page.on("request", (req) => {
    if (/70123456/.test(req.url())) fake.phoneInUrl = true;
  });

  await page.route(/\/api\/v1\/admin\/cash-blocks(\?.*)?$/, (route) => {
    const active = new URL(route.request().url()).searchParams.get("active");
    const items = fake.blocks.filter((b) => active === null || String(b.active) === active);
    return json(route, { items, next_cursor: null });
  });
  await page.route(/\/api\/v1\/admin\/cash-blocks\/search$/, (route) => {
    log(route);
    const body = JSON.parse(route.request().postData() ?? "{}") as { phone?: string };
    if (!/^\d{8}$/.test(body.phone ?? "")) return route.fulfill(problem(422, "VALIDATION_ERROR"));
    return json(route, { items: fake.blocks.filter((b) => b.id === "b-2"), next_cursor: null });
  });
  await page.route(/\/api\/v1\/admin\/cash-blocks\/[^/]+\/clear$/, (route) => {
    log(route);
    if (route.request().headers()["x-csrf-token"] !== "e2e-csrf-value") return route.fulfill(problem(403, "CSRF_INVALID"));
    const id = new URL(route.request().url()).pathname.split("/").at(-2);
    const b = fake.blocks.find((x) => x.id === id)!;
    Object.assign(b, { active: false, cleared_at: "2026-11-12T09:00:00Z", cleared_by: "admin-1" });
    return json(route, b);
  });

  await page.route(/\/api\/v1\/admin\/orders\/[^/?]+$/, (route) => json(route, order(fake)));
  await page.route(/\/api\/v1\/admin\/orders\/[^/]+\/chargebacks$/, (route) => {
    if (route.request().method() !== "POST") return json(route, fake.chargebacks);
    log(route);
    const body = JSON.parse(route.request().postData() ?? "{}") as { charged_cents: number; items: { amount_cents: number }[]; received_at: string };
    const total = body.items.reduce((s, i) => s + i.amount_cents, 0);
    if (body.items.length > 0 && total !== body.charged_cents) {
      return route.fulfill(problem(422, "CHARGEBACK_ALLOCATION_INVALID", { available: { lines: [{ order_item_id: LINE_ID, balance_cents: 3600 }], payment_cents: 3600, chargeable_cents: body.charged_cents } }));
    }
    const cb = { id: "cb-1", payment_id: PAY_ID, charged: usd(body.charged_cents), applied_cents: body.charged_cents, excess_cents: 0, received_at: body.received_at };
    fake.chargebacks.push(cb);
    return json(route, { ...cb, order_id: ORDER_ID }, 201);
  });

  await page.route(/\/api\/v1\/admin\/payments\/[^/?]+$/, (route) =>
    json(route, {
      payment: { id: UNPAID_PAY, order_id: UNPAID_ORDER, order_number: "B3D-UNPD0003", provider: "mock", status: "pending", amount_cents: 3600, currency: "USD", captured_amount_cents: null, captured_currency: null, provider_payment_id: null, initiated_at: "2026-11-09T10:00:00Z", verified_at: null, failed_at: null, expired_at: null, late_captured_at: null, needs_manual_confirmation: false, unprocessed_event_count: 1 },
      order: { id: UNPAID_ORDER, order_number: "B3D-UNPD0003", status: "pending_payment", total_cents: 3600, currency: "USD", placed_at: "2026-11-09T10:00:00Z", cancelled_at: null, hold_expires_at: "2026-11-09T10:30:00Z", manual_release_available_at: "2026-11-10T10:30:00Z" },
      events: [], history: [], available_actions: ["reconcile", "release_order"],
    })
  );
  await page.route(/\/api\/v1\/admin\/orders\/[^/]+\/release$/, (route) => {
    log(route);
    const body = JSON.parse(route.request().postData() ?? "{}") as { events_reviewed?: boolean };
    if (!body.events_reviewed) return route.fulfill(problem(409, "INVALID_STATE_TRANSITION", { reason: "unprocessed_events", count: 1 }));
    return json(route, { order_id: UNPAID_ORDER, status: "cancelled", cancelled_at: "2026-11-12T09:00:00Z", attempts_expired: [UNPAID_PAY], events_dismissed: [] });
  });
  return fake;
}

test.describe("Admin operations (Phase 6A)", () => {
  test("cash blocks: list, phone search in the POST body only, clear with confirmation", async ({ page }) => {
    const fake = await install(page);
    await page.goto("/admin/cash-blocks");
    await expect(page.getByRole("navigation", { name: "Admin" }).getByRole("link", { name: "Cash blocks" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("link", { name: /^B3D-/ })).toHaveText(["B3D-REFU0001", "B3D-NOSH0002"]);
    await page.getByLabel("Find by contact phone").fill("123");
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText("Enter a valid Lebanese phone number.");
    await page.getByLabel("Find by contact phone").fill("70123456");
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.getByRole("link", { name: /^B3D-/ })).toHaveText(["B3D-NOSH0002"]);
    expect(fake.phoneInUrl).toBe(false);
    await page.getByRole("button", { name: "Clear search" }).click();
    await page.getByRole("row").filter({ hasText: "B3D-REFU0001" }).getByRole("button", { name: "Clear block" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Clear block" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(page.getByRole("link", { name: /^B3D-/ })).toHaveText(["B3D-NOSH0002"]);
    expect(fake.writes.at(-1)).toEqual(expect.objectContaining({ path: "/api/v1/admin/cash-blocks/b-1/clear", csrf: "e2e-csrf-value" }));
  });

  test("chargeback: server allocation refusal shows its figures; then recorded with a key", async ({ page }) => {
    const fake = await install(page);
    await page.goto(`/admin/orders/${ORDER_ID}`);
    await page.getByRole("button", { name: "Record a chargeback" }).click();
    const dialog = page.getByRole("dialog", { name: "Record a chargeback?" });
    await dialog.getByLabel("Provider dispute reference").fill("DSP-100");
    await dialog.getByLabel(/Amount charged back/).fill("20");
    await dialog.getByLabel("Received at").fill("2026-11-11T09:30");
    await dialog.getByLabel("Reason").fill("Customer disputed");
    await dialog.getByLabel(/^Articulated Dragon/).fill("5");
    await dialog.getByRole("button", { name: "Record chargeback" }).click();
    await expect(dialog.getByRole("alert")).toContainText("must add up");
    await expect(dialog).toContainText(/Items must total\s*\$20\.00/);
    await dialog.getByLabel(/^Articulated Dragon/).fill("20");
    await dialog.getByRole("button", { name: "Record chargeback" }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByText("Chargeback recorded.")).toBeVisible();
    const posts = fake.writes.filter((w) => w.path.endsWith("/chargebacks"));
    expect(posts).toHaveLength(2);
    expect(posts[1]!.key).toMatch(/^[A-Za-z0-9._:-]{8,255}$/);
    expect(posts[1]!.key).not.toBe(posts[0]!.key);
    expect(JSON.parse(posts[1]!.body!)).toEqual(expect.objectContaining({ payment_id: PAY_ID, charged_cents: 2000, items: [{ order_item_id: LINE_ID, amount_cents: 2000 }] }));
  });

  test("manual release: offered by the server's action; unprocessed events need the review tick", async ({ page }) => {
    const fake = await install(page);
    await page.goto(`/admin/payments/${UNPAID_PAY}`);
    await page.getByRole("button", { name: "Release order" }).click();
    const dialog = page.getByRole("dialog", { name: "Release this unpaid order?" });
    await dialog.getByLabel("Reason").fill("Customer never completed payment.");
    await dialog.getByRole("button", { name: "Release order" }).click();
    await expect(dialog).toContainText("Confirm you reviewed the provider events.");
    expect(fake.writes.filter((w) => w.path.endsWith("/release"))).toHaveLength(0);
    await dialog.getByRole("checkbox").check();
    await dialog.getByRole("button", { name: "Release order" }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByText("The order was released.")).toBeVisible();
    expect(JSON.parse(fake.writes.at(-1)!.body!)).toEqual({ reason: "Customer never completed payment.", events_reviewed: true });
  });
});
