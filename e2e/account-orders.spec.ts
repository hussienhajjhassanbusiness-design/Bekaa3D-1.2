import { test, expect, type Page } from "@playwright/test";
import { stubEmptyCart } from "./support/stubCart";

// Phase 5E — /account/orders and /account/orders/[id] (FVS-029) against a
// deterministic, in-memory stand-in for backend 2dfb27b's customer order
// contract (openapi.json /api/v1/me/orders, /api/v1/me/orders/{order_id};
// ordering/api/orders.py; docs/order-history.md). Route interception only:
// no backend on :8000 and no media server on :8001 (lines have no image).
//
// The fake applies the documented rules: newest first, opaque cursor,
// `limit` honoured, next_cursor null on the last page; an id that is not
// the caller's own is 404 NOT_FOUND (the same body as an unknown id);
// anonymous is 401 AUTH_REQUIRED and refresh fails.
//
// Route patterns are exact: `/api/v1/me`, `/api/v1/me/orders`,
// `/api/v1/me/orders/{id}`, `/api/v1/settings/public`, `/api/v1/auth/refresh`.

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

const usd = (amount_cents: number) => ({ amount_cents, currency: "USD" });
const uuid = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;

const CASH_ID = uuid(1);
const ONLINE_ID = uuid(2);
const STL_ID = uuid(3);
const MIXED_ID = uuid(4);
// Exists in the "database" but belongs to another customer.
const FOREIGN_ID = uuid(99);

type Json = Record<string, unknown>;

function line(overrides: Json = {}): Json {
  return {
    id: "l-phys",
    product_id: "p-dragon",
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
    ...overrides,
  };
}

function stlLine(overrides: Json = {}): Json {
  return line({
    id: "l-stl",
    product_id: "p-dragon-stl",
    product_type: "stl",
    name: "Dragon STL",
    unit_price: usd(900),
    quantity: 1,
    line_total: usd(900),
    fulfillment_status: "awaiting_delivery",
    ...overrides,
  });
}

function detail(overrides: Json): Json {
  return {
    source: "cart",
    can_cancel: false,
    can_retry_payment: false,
    hold_expires_at: null,
    tax: usd(0),
    delivery_address: null,
    contact_phone: null,
    delivery_fee_note: null,
    estimated_dispatch_at: null,
    completed_at: null,
    cancelled_at: null,
    customer_note: null,
    payment: null,
    refunds: [],
    ...overrides,
  };
}

const ORDERS: Json[] = [
  detail({
    id: MIXED_ID,
    order_number: "B3D-2026-000004",
    status: "in_progress",
    fulfillment_method: "delivery",
    payment_method: "online",
    payment_due: false,
    amount_due: null,
    subtotal: usd(4500),
    total: usd(4500),
    delivery_address: { recipient_name: "Ada Lovelace", governorate: "beqaa", city: "Zahle", area: null, street: "Main St", landmark_notes: "Blue door" },
    contact_phone: "+96170123456",
    delivery_fee_note: "The delivery fee is paid to the courier on delivery.",
    estimated_dispatch_at: "2026-11-14T10:00:00Z",
    placed_at: "2026-11-09T10:00:00Z",
    lines: [line({ fulfillment_status: "shipped" }), stlLine({ fulfillment_status: "delivered", fulfilled_at: "2026-11-09T15:00:00Z" })],
    payment: { status: "paid", provider: "mock", amount: usd(4500) },
    status_history: [
      { order_item_id: null, from_status: null, to_status: "pending_payment", at: "2026-11-09T10:00:00Z" },
      { order_item_id: null, from_status: "pending_payment", to_status: "in_progress", at: "2026-11-09T10:05:00Z" },
      { order_item_id: "l-stl", from_status: "awaiting_delivery", to_status: "delivered", at: "2026-11-09T15:00:00Z" },
      { order_item_id: "l-phys", from_status: "ready_to_ship", to_status: "shipped", at: "2026-11-10T09:00:00Z" },
    ],
  }),
  detail({
    id: STL_ID,
    order_number: "B3D-2026-000003",
    status: "in_progress",
    fulfillment_method: null,
    payment_method: "online",
    payment_due: false,
    amount_due: null,
    subtotal: usd(900),
    total: usd(900),
    placed_at: "2026-11-09T12:00:00Z",
    lines: [stlLine()],
    payment: { status: "paid", provider: "mock", amount: usd(900) },
    status_history: [{ order_item_id: null, from_status: "pending_payment", to_status: "in_progress", at: "2026-11-09T12:01:00Z" }],
  }),
  detail({
    id: ONLINE_ID,
    order_number: "B3D-2026-000002",
    status: "pending_payment",
    fulfillment_method: "pickup",
    payment_method: "online",
    payment_due: false,
    amount_due: null,
    // A live (pending) attempt: the backend reports can_retry_payment false.
    can_retry_payment: false,
    hold_expires_at: "2026-11-10T11:00:00Z",
    subtotal: usd(3600),
    total: usd(3600),
    contact_phone: "+96171999888",
    estimated_dispatch_at: "2026-11-13T10:00:00Z",
    placed_at: "2026-11-10T10:30:00Z",
    lines: [line()],
    payment: { status: "pending", provider: "mock", amount: usd(3600) },
    status_history: [{ order_item_id: null, from_status: null, to_status: "pending_payment", at: "2026-11-10T10:30:00Z" }],
  }),
  detail({
    id: CASH_ID,
    order_number: "B3D-2026-000001",
    status: "in_progress",
    fulfillment_method: "delivery",
    payment_method: "cash",
    payment_due: true,
    amount_due: usd(3600),
    can_cancel: true,
    subtotal: usd(3600),
    total: usd(3600),
    delivery_address: { recipient_name: "Ada Lovelace", governorate: "beqaa", city: "Zahle", area: null, street: "Main St", landmark_notes: "Blue door" },
    contact_phone: "+96170123456",
    delivery_fee_note: "The delivery fee is paid to the courier on delivery.",
    estimated_dispatch_at: "2026-11-14T10:00:00Z",
    placed_at: "2026-11-11T10:00:00Z",
    customer_note: "Please call first",
    lines: [line()],
    status_history: [{ order_item_id: null, from_status: null, to_status: "in_progress", at: "2026-11-11T10:00:00Z" }],
  }),
];

function summaryOf(order: Json): Json {
  const keys = ["id", "order_number", "status", "payment_method", "fulfillment_method", "payment_due", "amount_due", "total", "placed_at"];
  return Object.fromEntries(keys.map((k) => [k, order[k]]));
}

function problem(status: number, code: string) {
  return {
    status,
    contentType: "application/problem+json",
    body: JSON.stringify({ type: "about:blank", title: "RAW TITLE", status, detail: "RAW DETAIL", code, errors: [] }),
  };
}

interface FakeOrders {
  listCalls: URL[];
  detailCalls: string[];
}

async function installFakeBackend(page: Page, options: { orders?: Json[]; pageSize?: number } = {}): Promise<FakeOrders> {
  const orders = [...(options.orders ?? ORDERS)].sort((a, b) => String(b.placed_at).localeCompare(String(a.placed_at)));
  const fake: FakeOrders = { listCalls: [], detailCalls: [] };

  // A signed-in browser has the csrf_token cookie; without it the auth
  // bootstrap treats the visitor as anonymous without calling /me.
  await page.context().addCookies([{ name: "csrf_token", value: "e2e-csrf-value", url: "http://localhost:3000" }]);
  // The header's cart count reads /api/v1/cart on every page.
  await stubEmptyCart(page);
  await page.route(/\/api\/v1\/me$/, (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(ME) }));
  await page.route(/\/api\/v1\/settings\/public$/, (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(SETTINGS) })
  );
  await page.route(/\/api\/v1\/me\/orders(\?.*)?$/, (route) => {
    const url = new URL(route.request().url());
    fake.listCalls.push(url);
    // The test-chosen page size overrides the client's, to exercise paging with few orders.
    const limit = options.pageSize ?? Number(url.searchParams.get("limit") ?? 20);
    const cursor = url.searchParams.get("cursor");
    const start = cursor ? Number(Buffer.from(cursor, "base64url").toString()) : 0;
    const items = orders.slice(start, start + limit).map(summaryOf);
    const next = start + limit < orders.length ? Buffer.from(String(start + limit)).toString("base64url") : null;
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ items, next_cursor: next }) });
  });
  await page.route(/\/api\/v1\/me\/orders\/[^/?]+$/, (route) => {
    const id = decodeURIComponent(new URL(route.request().url()).pathname.split("/").pop() ?? "");
    fake.detailCalls.push(id);
    // Another customer's order and an unknown id get the same 404 body.
    const order = orders.find((o) => o.id === id);
    return route.fulfill(order ? { contentType: "application/json", body: JSON.stringify(order) } : problem(404, "NOT_FOUND"));
  });
  return fake;
}

async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

const card = (page: Page, number: string) => page.getByRole("listitem").filter({ hasText: `Order ${number}` });

test.describe("Account orders (Phase 5E / FVS-029)", () => {
  test("an anonymous visit redirects to /login with a safe returnTo", async ({ page }) => {
    await stubEmptyCart(page);
    // An expired session: the cookie is present, /me and the refresh are refused.
    await page.context().addCookies([{ name: "csrf_token", value: "e2e-csrf-value", url: "http://localhost:3000" }]);
    await page.route(/\/api\/v1\/me$/, (route) => route.fulfill(problem(401, "AUTH_REQUIRED")));
    await page.route(/\/api\/v1\/auth\/refresh$/, (route) => route.fulfill(problem(401, "AUTH_REQUIRED")));
    let orderCalls = 0;
    await page.route(/\/api\/v1\/me\/orders/, (route) => {
      orderCalls += 1;
      return route.fulfill(problem(401, "AUTH_REQUIRED"));
    });
    await page.goto(`/account/orders/${CASH_ID}`);
    await expect(page).toHaveURL(new RegExp(`/login\\?returnTo=%2Faccount%2Forders%2F${CASH_ID}$`));
    expect(orderCalls).toBe(0);
  });

  test("empty history points to the shop", async ({ page }) => {
    await installFakeBackend(page, { orders: [] });
    await page.goto("/account/orders");
    await expect(page.getByText("You haven't placed any orders yet.")).toBeVisible();
    await expect(page.getByRole("link", { name: "Browse the shop" })).toHaveAttribute("href", "/shop");
  });

  test("the account nav links to Orders; history is newest first with server-backed fields; reload keeps it", async ({ page }) => {
    await installFakeBackend(page);
    await page.goto("/account/profile");
    await page.getByRole("navigation", { name: "Account" }).getByRole("link", { name: "Orders" }).click();
    await expect(page).toHaveURL(/\/account\/orders$/);
    await expect(page.getByRole("link", { name: "Orders" })).toHaveAttribute("aria-current", "page");

    const numbers = await page.getByRole("link", { name: /^Order B3D-/ }).allTextContents();
    expect(numbers).toEqual(["Order B3D-2026-000001", "Order B3D-2026-000002", "Order B3D-2026-000003", "Order B3D-2026-000004"]);

    const cash = card(page, "B3D-2026-000001");
    await expect(cash).toContainText("In progress");
    await expect(cash).toContainText("Cash");
    await expect(cash).toContainText("Delivery");
    await expect(cash).toContainText(/Payment due in cash:\s*\$36\.00/);
    await expect(cash).not.toContainText(/\bpaid\b/i);

    const online = card(page, "B3D-2026-000002");
    await expect(online).toContainText("Awaiting payment");
    await expect(online).toContainText("Online payment");
    await expect(online).toContainText("Pickup");
    await expect(online).not.toContainText(/payment due|\bpaid\b/i);

    await expect(card(page, "B3D-2026-000003")).toContainText("STL files only");

    await page.reload();
    await expect(page.getByRole("link", { name: /^Order B3D-/ })).toHaveCount(4);
  });

  test("Load more pages with the server's cursor and stops on the last page", async ({ page }) => {
    const fake = await installFakeBackend(page, { pageSize: 3 });
    await page.goto("/account/orders");
    await expect(page.getByRole("link", { name: /^Order B3D-/ })).toHaveCount(3);
    await page.getByRole("button", { name: "Load more orders" }).click();
    await expect(page.getByRole("link", { name: /^Order B3D-/ })).toHaveCount(4);
    await expect(page.getByRole("button", { name: "Load more orders" })).toHaveCount(0);
    expect(fake.listCalls[0]!.searchParams.get("cursor")).toBeNull();
    expect(fake.listCalls.at(-1)!.searchParams.get("cursor")).toBeTruthy();
  });

  test("cash delivery order: amount due, never paid, delivery snapshot, no actions", async ({ page }) => {
    await installFakeBackend(page);
    await page.goto("/account/orders");
    await page.getByRole("link", { name: "Order B3D-2026-000001" }).click();
    await expect(page).toHaveURL(new RegExp(`/account/orders/${CASH_ID}$`));
    await expect(page.getByRole("heading", { level: 1, name: "Order B3D-2026-000001" })).toBeVisible();

    const payment = page.getByRole("region", { name: "Payment" });
    await expect(payment).toContainText("Cash");
    await expect(payment).toContainText(/Payment due in cash to the courier on delivery: \$36\.00/);
    await expect(payment).toContainText("This order hasn't been paid yet.");
    await expect(payment).not.toContainText("Payment status");
    await expect(page.getByText("Paid", { exact: true })).toHaveCount(0);

    const delivery = page.getByRole("region", { name: "Delivery" });
    await expect(delivery).toContainText("Ada Lovelace");
    await expect(delivery).toContainText("Main St");
    await expect(delivery).toContainText("+96170123456");
    await expect(page.getByRole("region", { name: "Summary" })).toContainText(/courier sets the delivery fee/);
    await expect(page.getByRole("region", { name: "Your note" })).toContainText("Please call first");
    await expect(page.getByText("RAW DETAIL")).toHaveCount(0);
    // can_cancel is true: the one control is FVS-031's Cancel order, in its own
    // section (the flow itself is covered in account-order-actions.spec.ts).
    await expect(page.getByRole("article").getByRole("button")).toHaveCount(1);
    await expect(page.getByRole("region", { name: "Order actions" }).getByRole("button", { name: "Cancel order" })).toBeVisible();

    await page.reload();
    await expect(page.getByRole("heading", { level: 1, name: "Order B3D-2026-000001" })).toBeVisible();
  });

  test("pending online pickup order: awaiting payment with its hold time; no retry while the attempt is live", async ({ page }) => {
    await installFakeBackend(page);
    await page.goto(`/account/orders/${ONLINE_ID}`);
    const payment = page.getByRole("region", { name: "Payment" });
    await expect(payment).toContainText("Online payment");
    await expect(payment.getByText("Awaiting payment")).toBeVisible();
    await expect(payment).toContainText("hasn't been confirmed as paid");
    await expect(payment).toContainText("may be released after");
    await expect(page.getByText("Paid", { exact: true })).toHaveCount(0);
    // A live attempt: can_retry_payment is false, so no retry (FVS-027 retry is covered in payment-result.spec.ts).
    await expect(page.getByRole("button", { name: /pay|retry/i })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /pay|retry|continue/i })).toHaveCount(0);

    const pickup = page.getByRole("region", { name: "Pickup" });
    await expect(pickup).toContainText("You'll collect this order from us.");
    await expect(pickup).toContainText("Bekaa3D workshop, Zahle");
    await expect(pickup).toContainText("+96171999888");
    await expect(page.getByText(/courier sets the delivery fee/)).toHaveCount(0);
  });

  test("STL-only order: emailed manually, no download anywhere", async ({ page }) => {
    await installFakeBackend(page);
    await page.goto(`/account/orders/${STL_ID}`);
    const items = page.getByRole("region", { name: "Items" });
    await expect(items).toContainText("Dragon STL");
    await expect(items).toContainText("STL file, sent by email");
    await expect(items).toContainText("Paid, not yet emailed");
    await expect(items).toContainText("We'll email this file to you.");
    await expect(page.getByRole("region", { name: "Delivery" })).toContainText("nothing is shipped");
    await expect(page.getByText(/download/i)).toHaveCount(0);
    await expect(page.getByRole("link", { name: /download/i })).toHaveCount(0);
  });

  test("mixed order: physical shipped, STL emailed with its date, paid only per the server, history in order", async ({ page }) => {
    await installFakeBackend(page);
    await page.goto(`/account/orders/${MIXED_ID}`);
    const items = page.getByRole("region", { name: "Items" });
    await expect(items).toContainText("Articulated Dragon");
    await expect(items).toContainText("Shipped");
    await expect(items).toContainText("Emailed");
    await expect(items).toContainText(/Emailed to you on 9 November 2026/);
    await expect(page.getByRole("region", { name: "Payment" }).getByText("Paid", { exact: true })).toBeVisible();
    const updates = page.getByRole("region", { name: "Order updates" }).getByRole("listitem");
    await expect(updates).toHaveCount(4);
    await expect(updates.nth(0)).toContainText("Order: Awaiting payment");
    await expect(updates.nth(2)).toContainText("Dragon STL: Emailed");
    await expect(updates.nth(3)).toContainText("Articulated Dragon: Shipped");
  });

  test("unknown, another customer's and malformed ids all show the same not-found page", async ({ page }) => {
    const fake = await installFakeBackend(page);
    for (const id of [uuid(777), FOREIGN_ID]) {
      await page.goto(`/account/orders/${id}`);
      await expect(page.getByRole("heading", { name: "Order not found" })).toBeVisible();
      await expect(page.getByText("RAW DETAIL")).toHaveCount(0);
    }
    expect(fake.detailCalls).toEqual([uuid(777), FOREIGN_ID]);

    await page.goto("/account/orders/not-a-real-id");
    await expect(page.getByRole("heading", { name: "Order not found" })).toBeVisible();
    expect(fake.detailCalls).toHaveLength(2);
    await page.getByRole("link", { name: "View your orders" }).click();
    await expect(page).toHaveURL(/\/account\/orders$/);
  });

  test("a server failure shows safe copy and retries", async ({ page }) => {
    await installFakeBackend(page);
    let fail = true;
    await page.route(/\/api\/v1\/me\/orders(\?.*)?$/, (route) =>
      fail ? route.fulfill(problem(500, "INTERNAL_ERROR")) : route.fallback()
    );
    await page.goto("/account/orders");
    await expect(page.getByRole("alert").filter({ hasText: "We couldn't load your orders" })).toContainText("Please try again.");
    await expect(page.getByText(/RAW/)).toHaveCount(0);
    fail = false;
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByRole("link", { name: /^Order B3D-/ })).toHaveCount(4);
  });

  test("mobile width: history and detail have no horizontal scroll", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await installFakeBackend(page);
    await page.goto("/account/orders");
    await expect(page.getByRole("link", { name: /^Order B3D-/ })).toHaveCount(4);
    await noHorizontalScroll(page);
    await page.goto(`/account/orders/${MIXED_ID}`);
    await expect(page.getByRole("heading", { level: 1, name: "Order B3D-2026-000004" })).toBeVisible();
    await noHorizontalScroll(page);
  });

  test("keyboard only: open an order from the history and return", async ({ page }) => {
    await installFakeBackend(page);
    await page.goto("/account/orders");
    const first = page.getByRole("link", { name: "Order B3D-2026-000001" });
    await expect(first).toBeVisible();
    for (let i = 0; i < 40; i += 1) {
      await page.keyboard.press("Tab");
      if (await first.evaluate((el) => el === document.activeElement)) break;
    }
    await expect(first).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(new RegExp(`/account/orders/${CASH_ID}$`));

    const back = page.getByRole("link", { name: "Back to your orders" });
    for (let i = 0; i < 40; i += 1) {
      await page.keyboard.press("Tab");
      if (await back.evaluate((el) => el === document.activeElement)) break;
    }
    await expect(back).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/account\/orders$/);
  });
});
