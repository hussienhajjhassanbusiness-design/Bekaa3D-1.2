import { test, expect, type Page, type Route } from "@playwright/test";
import { E2E_ORIGIN } from "./support/origin";

// Phase 5D — /checkout (FVS-026) against a deterministic, in-memory
// stand-in for backend 2dfb27b's contract (openapi.json /api/v1/checkout;
// ordering/api/checkout.py; docs/checkout.md). Route interception only: no
// backend on :8000 and no media server on :8001 (products have no images).
//
// The fake applies the documented rules: X-CSRF-Token must match; the
// Idempotency-Key header is required and must match the backend pattern;
// the same key + same body replays the stored 201 with
// Idempotent-Replayed; a different body under a stored key is 409
// IDEMPOTENCY_KEY_CONFLICT; the fulfillment matrix (delivery = address and
// no phone; pickup = phone and no address; STL-only = neither); cash needs
// every line physical, cash terms, and a live total within the cap; a live
// price that differs from the snapshot needs an exact acceptance (409
// CART_PRICE_CHANGED); an owned STL is dropped and named; a refusal leaves
// the cart untouched; a 201 clears the cart.
//
// Route patterns are exact (`/api/v1/cart`, `/api/v1/checkout`,
// `/api/v1/me/addresses`, `/api/v1/me`, `/api/v1/settings/public`).

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
  whatsapp_number: "+96170000000",
};

const ADDRESS = {
  id: "a-home",
  label: "Home",
  recipient_name: "Ada Lovelace",
  phone: "+96170123456",
  governorate: "beqaa",
  city: "Zahle",
  area: null,
  street: "Main St",
  landmark_notes: "Blue door",
  is_default: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

interface FakeProduct {
  id: string;
  type: "physical" | "stl";
  name: string;
  slug: string;
  priceCents: number;
  purchasable: boolean;
  maxQuantity: number | null;
}

const PRODUCTS: FakeProduct[] = [
  { id: "p-dragon", type: "physical", name: "Articulated Dragon", slug: "dragon", priceCents: 1800, purchasable: true, maxQuantity: 3 },
  { id: "p-dragon-stl", type: "stl", name: "Dragon STL", slug: "dragon-stl", priceCents: 900, purchasable: true, maxQuantity: null },
  { id: "p-vase", type: "physical", name: "Spiral Vase", slug: "spiral-vase", priceCents: 2200, purchasable: true, maxQuantity: 4 },
];

interface StoredLine {
  productId: string;
  quantity: number;
  snapshotCents: number;
}

interface CheckoutCall {
  key: string | undefined;
  csrf: string | undefined;
  body: Record<string, unknown>;
  replayed: boolean;
}

interface FakeBackend {
  lines: StoredLine[];
  owned: Set<string>;
  // product ids the server will refuse at checkout (an admin hid them after the cart loaded)
  refuseAtCheckout: Set<string>;
  calls: CheckoutCall[];
  stored: Map<string, { body: string; response: unknown }>;
  // Optional one-shot override for the next checkout request.
  next: ((route: Route) => Promise<void>) | null;
  orderSeq: number;
  cashMaxCents: number;
  // Phase 5E: placed orders by id, served on GET /api/v1/me/orders/{id}.
  orders: Map<string, Record<string, unknown>>;
}

// Real order ids are UUIDs (the order page refuses anything else).
function orderUuid(seq: number): string {
  return `00000000-0000-4000-8000-${String(seq).padStart(12, "0")}`;
}

function product(id: string): FakeProduct {
  return PRODUCTS.find((p) => p.id === id)!;
}

function problem(route: Route, status: number, code: string, extensions: Record<string, unknown> = {}, headers: Record<string, string> = {}) {
  return route.fulfill({
    status,
    contentType: "application/problem+json",
    headers,
    body: JSON.stringify({ type: "about:blank", title: "RAW TITLE", status, detail: "RAW DETAIL", code, errors: [], ...extensions }),
  });
}

function cartRead(backend: FakeBackend) {
  const items = backend.lines.map((line) => {
    const p = product(line.productId);
    return {
      product_id: p.id,
      product_type: p.type,
      name: p.name,
      slug: p.slug,
      cover_image: null,
      quantity: line.quantity,
      snapshot_price: { amount_cents: line.snapshotCents, currency: "USD" },
      current_price: { amount_cents: p.priceCents, currency: "USD" },
      price_changed: line.snapshotCents !== p.priceCents,
      max_quantity: p.maxQuantity,
      over_cap: false,
      purchasable: p.purchasable,
      unpurchasable_reason: p.purchasable ? null : "unavailable",
    };
  });
  return {
    id: items.length ? "cart-1" : null,
    items,
    contains_physical: items.some((i) => i.product_type === "physical"),
    contains_digital: items.some((i) => i.product_type === "stl"),
    updated_at: null,
  };
}

function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value as object)
      .sort()
      .map((k) => `${JSON.stringify(k)}:${stable((value as Record<string, unknown>)[k])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function placeOrder(backend: FakeBackend, body: Record<string, unknown>): { status: number; json: Record<string, unknown> } {
  const fail = (status: number, code: string, extensions: Record<string, unknown> = {}) => ({
    status,
    json: { type: "about:blank", title: "RAW TITLE", status, detail: "RAW DETAIL", code, errors: [], ...extensions },
  });

  if (backend.lines.length === 0) return fail(409, "CART_EMPTY", { dropped_lines: [] });
  const refused = backend.lines.filter((l) => backend.refuseAtCheckout.has(l.productId));
  if (refused.length) {
    return fail(422, "PRODUCT_NOT_PURCHASABLE", { lines: refused.map((l) => ({ product_id: l.productId, reason: "unavailable" })) });
  }
  const kept = backend.lines.filter((l) => !backend.owned.has(l.productId));
  const dropped = backend.lines.filter((l) => backend.owned.has(l.productId)).map((l) => l.productId);
  if (kept.length === 0) {
    return fail(409, "CART_EMPTY", { dropped_lines: dropped.map((product_id) => ({ product_id, reason: "already_owned" })) });
  }
  const physical = kept.some((l) => product(l.productId).type === "physical");
  const allPhysical = kept.every((l) => product(l.productId).type === "physical");
  const method = body.fulfillment_method;
  if (!physical) {
    if (method !== undefined || body.address_id !== undefined || body.contact_phone !== undefined) return fail(422, "INVALID_FULFILLMENT");
  } else if (method === "delivery") {
    if (body.address_id !== ADDRESS.id || body.contact_phone !== undefined) return fail(422, "INVALID_FULFILLMENT");
  } else if (method === "pickup") {
    if (body.address_id !== undefined || typeof body.contact_phone !== "string") return fail(422, "INVALID_FULFILLMENT");
  } else {
    return fail(422, "INVALID_FULFILLMENT");
  }
  if (body.payment_method === "cash" && !allPhysical) return fail(422, "PAYMENT_METHOD_NOT_ALLOWED", { reason: "cash_requires_physical" });

  const accepted = (body.accepted_price_changes as { product_id: string; amount_cents: number }[] | undefined) ?? [];
  const changes = kept
    .filter((l) => product(l.productId).priceCents !== l.snapshotCents)
    .filter((l) => !accepted.some((a) => a.product_id === l.productId && a.amount_cents === product(l.productId).priceCents))
    .map((l) => ({ product_id: l.productId, old_amount_cents: l.snapshotCents, new_amount_cents: product(l.productId).priceCents, currency: "USD" }));
  if (changes.length) return fail(409, "CART_PRICE_CHANGED", { price_changes: changes });

  const hasStl = kept.some((l) => product(l.productId).type === "stl");
  if (body.accept_terms !== true || (hasStl && body.accept_digital_final_sale !== true)) {
    return fail(422, "VALIDATION_ERROR");
  }
  const lines = kept.map((l, i) => {
    const p = product(l.productId);
    return {
      id: `line-${i}`,
      product_id: p.id,
      product_type: p.type,
      name: p.name,
      unit_price: { amount_cents: p.priceCents, currency: "USD" },
      quantity: l.quantity,
      line_total: { amount_cents: p.priceCents * l.quantity, currency: "USD" },
      fulfillment_status: "pending",
    };
  });
  const total = lines.reduce((sum, l) => sum + l.line_total.amount_cents, 0);
  const cash = body.payment_method === "cash";
  if (cash) {
    if (body.accept_cash_terms !== true) return fail(422, "VALIDATION_ERROR");
    if (total > backend.cashMaxCents) return fail(422, "CASH_PAYMENT_LIMIT_REACHED", { reason: "order_total" });
  }

  backend.orderSeq += 1;
  const number = `B3D-2026-${String(backend.orderSeq).padStart(6, "0")}`;
  backend.lines = [];
  const money = (amount_cents: number) => ({ amount_cents, currency: "USD" });
  return {
    status: 201,
    json: {
      order: {
        id: orderUuid(backend.orderSeq),
        order_number: number,
        source: "cart",
        status: cash ? "in_progress" : "pending_payment",
        payment_method: body.payment_method,
        fulfillment_method: physical ? method : null,
        subtotal: money(total),
        tax: money(0),
        total: money(total),
        placed_at: "2026-11-11T10:00:00Z",
        estimated_dispatch_at: physical ? "2026-11-14T10:00:00Z" : null,
        delivery_fee_note: method === "delivery" ? "The delivery fee is paid to the courier on delivery." : null,
        delivery_address:
          method === "delivery"
            ? { recipient_name: ADDRESS.recipient_name, governorate: ADDRESS.governorate, city: ADDRESS.city, area: null, street: ADDRESS.street, landmark_notes: ADDRESS.landmark_notes }
            : null,
        payment_due: cash,
        amount_due: cash ? money(total) : null,
        lines,
      },
      payment: cash ? null : { id: `pay-${backend.orderSeq}`, status: "pending", provider: "mock", redirect_url: `${E2E_ORIGIN}/checkout/return?order=${number}` },
      dropped_lines: dropped.map((product_id) => ({ product_id, reason: "already_owned" })),
    },
  };
}

async function installFakeBackend(page: Page, initial: StoredLine[], options: { settings?: Partial<typeof SETTINGS>; owned?: string[] } = {}) {
  const backend: FakeBackend = {
    lines: initial.map((l) => ({ ...l })),
    owned: new Set(options.owned ?? []),
    refuseAtCheckout: new Set(),
    calls: [],
    stored: new Map(),
    next: null,
    orderSeq: 122,
    orders: new Map(),
    cashMaxCents: (options.settings?.cash_max_order_total ?? SETTINGS.cash_max_order_total).amount_cents,
  };
  const settings = { ...SETTINGS, ...options.settings };

  await page.context().addCookies([{ name: "csrf_token", value: CSRF, url: E2E_ORIGIN }]);
  await page.route(/\/api\/v1\/me$/, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ME) }));
  await page.route(/\/api\/v1\/settings\/public$/, (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(settings) })
  );
  await page.route(/\/api\/v1\/me\/addresses$/, (route) =>
    route.request().method() === "GET"
      ? route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [ADDRESS] }) })
      : problem(route, 405, "METHOD_NOT_ALLOWED")
  );
  await page.route(/\/api\/v1\/cart$/, (route) =>
    route.request().method() === "GET"
      ? route.fulfill({ contentType: "application/json", body: JSON.stringify(cartRead(backend)) })
      : problem(route, 405, "METHOD_NOT_ALLOWED")
  );
  await page.route(/\/api\/v1\/checkout$/, async (route) => {
    const request = route.request();
    if (request.method() !== "POST") return problem(route, 405, "METHOD_NOT_ALLOWED");
    const headers = request.headers();
    const body = request.postDataJSON() as Record<string, unknown>;
    const key = headers["idempotency-key"];
    const call: CheckoutCall = { key, csrf: headers["x-csrf-token"], body, replayed: false };
    backend.calls.push(call);

    if (backend.next) {
      const handler = backend.next;
      backend.next = null;
      return handler(route);
    }
    if (call.csrf !== CSRF) return problem(route, 403, "CSRF_INVALID");
    if (!key || !KEY_PATTERN.test(key)) return problem(route, 422, "VALIDATION_ERROR");

    const fingerprint = stable(body);
    const stored = backend.stored.get(key);
    if (stored) {
      if (stored.body !== fingerprint) return problem(route, 409, "IDEMPOTENCY_KEY_CONFLICT");
      call.replayed = true;
      return route.fulfill({ status: 201, contentType: "application/json", headers: { "Idempotent-Replayed": "true" }, body: JSON.stringify(stored.response) });
    }
    const result = placeOrder(backend, body);
    if (result.status === 201) {
      backend.stored.set(key, { body: fingerprint, response: result.json });
      const placed = result.json as unknown as Parameters<typeof orderDetailFrom>[0];
      backend.orders.set(String(placed.order.id), orderDetailFrom(placed));
    }
    return route.fulfill({
      status: result.status,
      contentType: result.status === 201 ? "application/json" : "application/problem+json",
      body: JSON.stringify(result.json),
    });
  });
  // Phase 5E: the customer order detail for orders placed in this fake.
  await page.route(/\/api\/v1\/me\/orders\/[^/?]+$/, (route) => {
    const id = decodeURIComponent(new URL(route.request().url()).pathname.split("/").pop() ?? "");
    const order = backend.orders.get(id);
    return order
      ? route.fulfill({ contentType: "application/json", body: JSON.stringify(order) })
      : problem(route, 404, "NOT_FOUND");
  });
  // The mock provider's return page is a real frontend route; nothing to intercept.
  return backend;
}

// OrderDetailRead for a just-placed order, as GET /me/orders/{id} returns it.
function orderDetailFrom(read: { order: Record<string, unknown>; payment: { status: string; provider: string } | null }) {
  const order = read.order as Record<string, unknown> & { lines: Record<string, unknown>[]; total: unknown; status: string; fulfillment_method: string | null };
  return {
    ...order,
    can_cancel: false,
    can_retry_payment: false,
    hold_expires_at: order.status === "pending_payment" ? "2026-11-11T10:30:00Z" : null,
    contact_phone: order.fulfillment_method ? ADDRESS.phone : null,
    completed_at: null,
    cancelled_at: null,
    customer_note: null,
    lines: order.lines.map((line) => ({
      ...line,
      image_url: null,
      fulfilled_at: null,
      cancelled_at: null,
      receipt_confirmed_at: null,
      problem_reported_at: null,
    })),
    payment: read.payment ? { status: read.payment.status, provider: read.payment.provider, amount: order.total } : null,
    status_history: [{ order_item_id: null, from_status: null, to_status: order.status, at: "2026-11-11T10:00:00Z" }],
    refunds: [],
  };
}

const header = (page: Page) => page.getByRole("banner");

async function chooseDelivery(page: Page) {
  await page.getByRole("radio", { name: /^Delivery/ }).check();
  await expect(page.getByRole("radio", { name: /Home/ })).toBeChecked();
}

test.describe("Checkout (Phase 5D / FVS-026)", () => {
  test("an anonymous visit to /checkout redirects to /login with a safe returnTo", async ({ page }) => {
    await page.goto("/checkout");
    await expect(page).toHaveURL(/\/login\?returnTo=%2Fcheckout$/);
  });

  test("an empty cart cannot proceed", async ({ page }) => {
    const backend = await installFakeBackend(page, []);
    await page.goto("/checkout");
    await expect(page.getByText("Your cart is empty, so there's nothing to check out.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Place order" })).toHaveCount(0);
    expect(backend.calls).toEqual([]);
  });

  test("cart CTA → checkout; delivery + saved address + cash; response-backed confirmation; cart and header cleared", async ({ page }) => {
    const backend = await installFakeBackend(page, [{ productId: "p-dragon", quantity: 2, snapshotCents: 1800 }]);
    await page.goto("/cart");
    await expect(header(page).getByRole("link", { name: "Cart, 2 items" })).toBeVisible();
    await page.getByRole("link", { name: "Proceed to checkout" }).click();
    await expect(page).toHaveURL(/\/checkout$/);

    // No total is shown before the server prices the order.
    await expect(page.getByText("$36.00")).toHaveCount(0);
    await chooseDelivery(page);
    await expect(page.getByText(/pay it to them directly on delivery/)).toBeVisible();
    await page.getByRole("radio", { name: /Pay in cash/ }).check();
    await page.getByRole("checkbox", { name: /terms of sale/ }).check();
    await page.getByRole("checkbox", { name: /pay the full amount in cash/ }).check();
    await page.getByRole("button", { name: "Place order" }).click();

    await expect(page.getByRole("heading", { name: "Order placed" })).toBeVisible();
    await expect(page.getByText("B3D-2026-000123")).toBeVisible();
    await expect(page.getByText(/Payment due in cash to the courier on delivery/)).toContainText("$36.00");
    await expect(page.getByText(/hasn't been paid yet/)).toBeVisible();
    expect(backend.calls).toHaveLength(1);
    expect(backend.calls[0]!.body).toEqual({
      payment_method: "cash",
      fulfillment_method: "delivery",
      address_id: "a-home",
      accept_terms: true,
      accept_cash_terms: true,
    });
    expect(backend.calls[0]!.key).toMatch(KEY_PATTERN);
    expect(backend.calls[0]!.csrf).toBe(CSRF);
    await expect(header(page).getByRole("link", { name: "Cart", exact: true })).toBeVisible();

    // Phase 5E: the confirmation opens the real order page, which shows the same unpaid cash order.
    await expect(page.getByRole("link", { name: "View order" })).toHaveAttribute("href", `/account/orders/${orderUuid(123)}`);
    await page.getByRole("link", { name: "View order" }).click();
    await expect(page).toHaveURL(new RegExp(`/account/orders/${orderUuid(123)}$`));
    await expect(page.getByRole("heading", { level: 1, name: "Order B3D-2026-000123" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Payment" })).toContainText(/Payment due in cash to the courier on delivery: \$36\.00/);
    await page.goBack();
    await expect(page).toHaveURL(/\/checkout$/);

    // Reload: the confirmation was a one-time response; the cart stays empty and nothing is resubmitted.
    await page.reload();
    await expect(page.getByText("Your cart is empty, so there's nothing to check out.")).toBeVisible();
    expect(backend.calls).toHaveLength(1);
  });

  test("pickup + online (mock provider): phone, no address; follows the opaque redirect; the return page claims nothing", async ({ page }) => {
    const backend = await installFakeBackend(page, [{ productId: "p-vase", quantity: 1, snapshotCents: 2200 }]);
    await page.goto("/checkout");
    await page.getByRole("radio", { name: /^Pickup/ }).check();
    await expect(page.getByText("Bekaa3D workshop, Zahle")).toBeVisible();
    await expect(page.getByText("Mon-Fri 10:00-18:00")).toBeVisible();
    await page.getByLabel("Contact phone").fill("70 123 456");
    await page.getByRole("radio", { name: /Pay online/ }).check();
    await page.getByRole("checkbox", { name: /terms of sale/ }).check();
    await page.getByRole("button", { name: "Place order" }).click();

    await expect(page).toHaveURL("/checkout/return?order=B3D-2026-000123");
    await expect(page.getByText(/Your payment hasn't been confirmed yet\./)).toBeVisible();
    await expect(page.getByText(/payment (was )?successful/i)).toHaveCount(0);
    expect(backend.calls[0]!.body).toEqual({ payment_method: "online", fulfillment_method: "pickup", contact_phone: "70 123 456", accept_terms: true });
  });

  test("STL only: no fulfillment, final-sale consent, cash unavailable, online redirect", async ({ page }) => {
    const backend = await installFakeBackend(page, [{ productId: "p-dragon-stl", quantity: 1, snapshotCents: 900 }]);
    await page.goto("/checkout");
    await expect(page.getByText(/Your order only has STL files/)).toBeVisible();
    await expect(page.getByRole("radio", { name: /^Delivery/ })).toHaveCount(0);
    await expect(page.getByRole("radio", { name: /Pay in cash/ })).toBeDisabled();
    await page.getByRole("radio", { name: /Pay online/ }).check();
    await page.getByRole("checkbox", { name: /terms of sale/ }).check();
    await page.getByRole("checkbox", { name: /final sale/ }).check();
    await page.getByRole("button", { name: "Place order" }).click();
    await expect(page).toHaveURL(/\/checkout\/return\?order=/);
    expect(backend.calls[0]!.body).toEqual({ payment_method: "online", accept_terms: true, accept_digital_final_sale: true });
  });

  test("CART_PRICE_CHANGED: names the line, needs explicit acceptance, resubmits with accepted_price_changes under a new key", async ({ page }) => {
    const backend = await installFakeBackend(page, [{ productId: "p-dragon", quantity: 1, snapshotCents: 1500 }]);
    await page.goto("/checkout");
    await chooseDelivery(page);
    await page.getByRole("radio", { name: /Pay online/ }).check();
    await page.getByRole("checkbox", { name: /terms of sale/ }).check();
    await page.getByRole("button", { name: "Place order" }).click();

    const banner = page.getByRole("alert").filter({ hasText: "Some prices have changed" });
    await expect(banner).toContainText("Articulated Dragon");
    await expect(banner).toContainText("$15.00");
    await expect(banner).toContainText("$18.00");
    await expect(page.getByText("RAW DETAIL")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Place order" })).toBeDisabled();
    expect(backend.calls).toHaveLength(1);

    await page.getByRole("button", { name: "Accept new prices" }).click();
    expect(backend.calls).toHaveLength(1);
    await page.getByRole("button", { name: "Place order" }).click();
    await expect(page).toHaveURL(/\/checkout\/return\?order=/);
    expect(backend.calls).toHaveLength(2);
    expect(backend.calls[1]!.body.accepted_price_changes).toEqual([{ product_id: "p-dragon", amount_cents: 1800, currency: "USD" }]);
    expect(backend.calls[1]!.key).not.toBe(backend.calls[0]!.key);
  });

  test("a line refused at checkout is named; the cart is untouched and still shown in /cart", async ({ page }) => {
    const backend = await installFakeBackend(page, [
      { productId: "p-dragon", quantity: 1, snapshotCents: 1800 },
      { productId: "p-vase", quantity: 1, snapshotCents: 2200 },
    ]);
    backend.refuseAtCheckout.add("p-vase");
    await page.goto("/checkout");
    await chooseDelivery(page);
    await page.getByRole("radio", { name: /Pay online/ }).check();
    await page.getByRole("checkbox", { name: /terms of sale/ }).check();
    await page.getByRole("button", { name: "Place order" }).click();

    const notice = page.getByRole("alert").filter({ hasText: "can't be ordered right now" });
    await expect(notice).toContainText("Spiral Vase is currently unavailable.");
    await expect(page.getByRole("heading", { name: /Order placed|awaiting payment/ })).toHaveCount(0);
    await notice.getByRole("link", { name: "Review your cart" }).click();
    await expect(page.getByRole("article", { name: "Spiral Vase" })).toBeVisible();
    await expect(page.getByRole("article", { name: "Articulated Dragon" })).toBeVisible();
    expect(backend.lines).toHaveLength(2);
  });

  test("dropped (already owned) STL: the order says it wasn't charged and waits for Continue to payment", async ({ page }) => {
    const backend = await installFakeBackend(
      page,
      [
        { productId: "p-dragon", quantity: 1, snapshotCents: 1800 },
        { productId: "p-dragon-stl", quantity: 1, snapshotCents: 900 },
      ],
      { owned: ["p-dragon-stl"] }
    );
    await page.goto("/checkout");
    await chooseDelivery(page);
    await page.getByRole("radio", { name: /Pay online/ }).check();
    await page.getByRole("checkbox", { name: /terms of sale/ }).check();
    await page.getByRole("checkbox", { name: /final sale/ }).check();
    await page.getByRole("button", { name: "Place order" }).click();

    await expect(page.getByRole("heading", { name: "Your order is awaiting payment" })).toBeVisible();
    await expect(page.getByText(/not included in your order because you already own them/)).toBeVisible();
    await expect(page.getByRole("alert").getByText("Dragon STL")).toBeVisible();
    await expect(page.getByLabel("Order items")).not.toContainText("Dragon STL");
    await expect(page).toHaveURL(/\/checkout$/);
    await page.getByRole("button", { name: "Continue to payment" }).click();
    await expect(page).toHaveURL(/\/checkout\/return\?order=/);
    expect(backend.calls).toHaveLength(1);
  });

  test("a refusal (cash above the limit) preserves the cart and the form, with safe copy", async ({ page }) => {
    const backend = await installFakeBackend(page, [{ productId: "p-vase", quantity: 4, snapshotCents: 2200 }], {
      settings: { cash_max_order_total: { amount_cents: 5000, currency: "USD" } },
    });
    await page.goto("/checkout");
    await chooseDelivery(page);
    await page.getByRole("radio", { name: /Pay in cash/ }).check();
    await page.getByRole("checkbox", { name: /terms of sale/ }).check();
    await page.getByRole("checkbox", { name: /pay the full amount in cash/ }).check();
    await page.getByRole("button", { name: "Place order" }).click();

    await expect(page.getByText("This order is above the $50.00 limit for cash payment. Please pay online.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Place order" })).toBeEnabled();
    expect(backend.lines).toHaveLength(1);
    await expect(header(page).getByRole("link", { name: "Cart, 4 items" })).toBeVisible();

    // Switching to online is a new body, so a new key; it succeeds.
    await page.getByRole("radio", { name: /Pay online/ }).check();
    await page.getByRole("button", { name: "Place order" }).click();
    await expect(page).toHaveURL(/\/checkout\/return\?order=/);
    expect(backend.calls[1]!.key).not.toBe(backend.calls[0]!.key);
  });

  test("an unknown outcome (connection dropped) retries with the SAME key and body and never duplicates the order", async ({ page }) => {
    const backend = await installFakeBackend(page, [{ productId: "p-dragon", quantity: 1, snapshotCents: 1800 }]);
    await page.goto("/checkout");
    await chooseDelivery(page);
    await page.getByRole("radio", { name: /Pay in cash/ }).check();
    await page.getByRole("checkbox", { name: /terms of sale/ }).check();
    await page.getByRole("checkbox", { name: /pay the full amount in cash/ }).check();
    // The server places the order but the response never arrives.
    backend.next = async (route) => {
      const call = backend.calls.at(-1)!;
      const result = placeOrder(backend, call.body);
      backend.stored.set(call.key!, { body: stable(call.body), response: result.json });
      await route.abort("connectionreset");
    };
    await page.getByRole("button", { name: "Place order" }).click();
    await expect(page.getByText(/couldn't confirm whether your order was placed/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Place order" })).toHaveCount(0);

    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByRole("heading", { name: "Order placed" })).toBeVisible();
    await expect(page.getByText("B3D-2026-000123")).toBeVisible();
    expect(backend.calls).toHaveLength(2);
    expect(backend.calls[1]!.key).toBe(backend.calls[0]!.key);
    expect(backend.calls[1]!.body).toEqual(backend.calls[0]!.body);
    expect(backend.calls[1]!.replayed).toBe(true);
    expect(backend.orderSeq).toBe(123);
  });

  test("CSRF rejection: safe copy, cart kept", async ({ page }) => {
    const backend = await installFakeBackend(page, [{ productId: "p-dragon", quantity: 1, snapshotCents: 1800 }]);
    await page.context().addCookies([{ name: "csrf_token", value: "stale-value", url: E2E_ORIGIN }]);
    await page.goto("/checkout");
    await chooseDelivery(page);
    await page.getByRole("radio", { name: /Pay online/ }).check();
    await page.getByRole("checkbox", { name: /terms of sale/ }).check();
    await page.getByRole("button", { name: "Place order" }).click();
    await expect(page.getByText("Unable to verify your session. Please refresh the page and try again.")).toBeVisible();
    expect(backend.lines).toHaveLength(1);
    expect(backend.calls[0]!.csrf).toBe("stale-value");
  });

  test("keyboard only: choose, consent and place an order", async ({ page }) => {
    const backend = await installFakeBackend(page, [{ productId: "p-dragon", quantity: 1, snapshotCents: 1800 }]);
    await page.goto("/checkout");
    await page.getByRole("radio", { name: /^Delivery/ }).focus();
    await page.keyboard.press("Space");
    await expect(page.getByRole("radio", { name: /Home/ })).toBeChecked();
    await page.getByRole("radio", { name: /Pay online/ }).focus();
    await page.keyboard.press("Space");
    await page.getByRole("checkbox", { name: /terms of sale/ }).focus();
    await page.keyboard.press("Space");
    // Tab forward to the submit button and press Enter.
    for (let i = 0; i < 5; i += 1) {
      const focused = await page.evaluate(() => document.activeElement?.textContent ?? "");
      if (focused.trim() === "Place order") break;
      await page.keyboard.press("Tab");
    }
    await expect(page.getByRole("button", { name: "Place order" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/checkout\/return\?order=/);
    expect(backend.calls).toHaveLength(1);
  });

  test("mobile width: no horizontal scroll, and checkout completes", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    const backend = await installFakeBackend(page, [{ productId: "p-dragon", quantity: 1, snapshotCents: 1800 }]);
    await page.goto("/checkout");
    await chooseDelivery(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await page.getByRole("radio", { name: /Pay in cash/ }).check();
    await page.getByRole("checkbox", { name: /terms of sale/ }).check();
    await page.getByRole("checkbox", { name: /pay the full amount in cash/ }).check();
    await page.getByRole("button", { name: "Place order" }).click();
    await expect(page.getByRole("heading", { name: "Order placed" })).toBeVisible();
    expect(backend.calls).toHaveLength(1);
  });
});
