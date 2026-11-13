import { test, expect, type Page, type Route } from "@playwright/test";
import { stubEmptyCart } from "./support/stubCart";

// Phase 5H — FVS-030 admin orders + fulfillment against a deterministic,
// stateful stand-in for backend 2dfb27b (fulfillment/api/admin_orders.py,
// item_transition.py, stl_deliveries.py; ordering/domain/line_transitions.py,
// handover.py). Route interception only: no backend on :8000, no media
// server on :8001.
//
// The fake follows the real rules: each line's `available_actions` come
// from the delivery/pickup/STL edge tables (cash lines never offer
// delivered/picked_up: that is the cash handover); the handover needs every
// live line at the ready state and the exact live total; writes need the
// X-CSRF-Token header; a customer gets 404 from the admin boundary.
//
// Exact route patterns: /api/v1/me, /api/v1/admin/orders(?…),
// /api/v1/admin/orders/{id}, …/items/{item}/transition, …/cash-handover,
// …/cancel, /api/v1/admin/stl-deliveries(?…).

type Json = Record<string, unknown>;
const usd = (amount_cents: number) => ({ amount_cents, currency: "USD" });
const uuid = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;

const ADMIN_ME = { id: "admin-1", email: "admin@example.com", role: "admin", email_verified: true, email_verified_at: "2025-01-01T00:00:00Z", created_at: "2024-01-01T00:00:00Z" };
const CUSTOMER_ME = { ...ADMIN_ME, id: "c-1", email: "rana@example.com", role: "customer" };

const CASH_ID = uuid(21);
const ONLINE_ID = uuid(22);
const STL_ORDER_ID = uuid(23);
const STL_LINE_ID = uuid(231);
const NOW = "2026-11-12T09:00:00Z";

const DELIVERY: Record<string, string[]> = {
  pending: ["in_production", "cancelled"],
  in_production: ["ready_to_ship", "cancelled"],
  ready_to_ship: ["shipped", "cancelled"],
  shipped: ["delivered", "returned"],
};
const CANCEL_REASONS: Record<string, string[]> = { ready_to_ship: ["refused", "other"] };

function actionsFor(order: Json, line: Json): Json[] {
  if (line.product_type === "stl") return line.fulfillment_status === "awaiting_delivery" ? [{ target_status: "delivered", cancel_reasons: [] }] : [];
  const edges = DELIVERY[String(line.fulfillment_status)] ?? [];
  return edges
    .filter((t) => !(order.payment_method === "cash" && t === "delivered"))
    .map((t) => ({ target_status: t, cancel_reasons: t === "cancelled" ? (CANCEL_REASONS[String(line.fulfillment_status)] ?? []) : [] }));
}

function line(id: string, overrides: Json = {}): Json {
  return {
    id, product_id: "p-1", product_type: "physical", name: "Articulated Dragon", image_url: null,
    unit_price: usd(1800), quantity: 2, line_total: usd(3600), fulfillment_status: "pending",
    fulfilled_at: null, delivered_by: null, cancelled_at: null, cancel_reason: null, offer_id: null,
    lead_time_days: 3, batch_size: null, receipt_confirmed_at: null, problem_reported_at: null, ...overrides,
  };
}

function order(id: string, number: string, overrides: Json = {}): Json {
  return {
    id, order_number: number, source: "cart", customer_id: "c-1", customer_email: "rana@example.com",
    status: "in_progress", fulfillment_method: "delivery", payment_method: "cash", payment_reached_paid: false,
    payment_due: true, amount_due: usd(3600), subtotal: usd(3600), tax: usd(0), total: usd(3600),
    delivery_address: { recipient_name: "Rana Haddad", governorate: "beqaa", city: "Zahle", area: null, street: "Main St 12", landmark_notes: null },
    contact_phone: "+96170123456", delivery_fee_note: "The courier collects the delivery fee.", customer_note: null,
    admin_note: null, estimated_dispatch_at: null, placed_at: "2026-11-11T10:00:00Z", completed_at: null, cancelled_at: null,
    lines: [line(uuid(211))], payments: [],
    status_history: [{ order_item_id: null, from_status: null, to_status: "in_progress", actor_user_id: "c-1", reason: null, at: "2026-11-11T10:00:00Z" }],
    refunds: [], chargebacks: [], refund_balance: null, ...overrides,
  };
}

function seed(): Json[] {
  return [
    order(CASH_ID, "B3D-CASH0001"),
    order(ONLINE_ID, "B3D-ONLN0002", {
      payment_method: "online", payment_reached_paid: true, payment_due: false, amount_due: null, placed_at: "2026-11-10T10:00:00Z",
      lines: [line(uuid(221), { fulfillment_status: "shipped" })],
      payments: [{ id: "pay-1", provider: "mock", status: "paid", amount: usd(3600), initiated_at: "2026-11-10T10:00:00Z", verified_at: "2026-11-10T10:01:00Z", late_captured_at: null, recorded_by: null }],
    }),
    order(STL_ORDER_ID, "B3D-STL00003", {
      fulfillment_method: null, payment_method: "online", payment_reached_paid: true, payment_due: false, amount_due: null,
      delivery_address: null, contact_phone: null, delivery_fee_note: null, placed_at: "2026-11-09T10:00:00Z",
      lines: [line(STL_LINE_ID, { product_type: "stl", name: "Dragon STL", quantity: 1, unit_price: usd(900), line_total: usd(900), fulfillment_status: "awaiting_delivery" })],
      total: usd(900), subtotal: usd(900),
    }),
  ];
}

function problem(status: number, code: string, extra: Json = {}) {
  return { status, contentType: "application/problem+json", body: JSON.stringify({ type: "about:blank", title: "RAW TITLE", status, detail: "RAW DETAIL", code, errors: [], ...extra }) };
}

interface Fake { orders: Json[]; writes: { path: string; body: Json | null; csrf: string | null }[] }

function view(o: Json): Json {
  return { ...o, lines: (o.lines as Json[]).map((l) => ({ ...l, available_actions: actionsFor(o, l) })) };
}

function summary(o: Json): Json {
  const keys = ["id", "order_number", "customer_id", "customer_email", "status", "fulfillment_method", "payment_method", "payment_due", "amount_due", "total", "estimated_dispatch_at", "placed_at"];
  return Object.fromEntries(keys.map((k) => [k, o[k]]));
}

function recompute(o: Json) {
  const live = (o.lines as Json[]).filter((l) => l.fulfillment_status !== "cancelled");
  if (live.length === 0) Object.assign(o, { status: "cancelled", payment_due: false, amount_due: null });
  else if (live.every((l) => ["delivered", "picked_up"].includes(String(l.fulfillment_status)))) Object.assign(o, { status: "completed", completed_at: NOW });
}

async function install(page: Page, me: Json = ADMIN_ME): Promise<Fake> {
  const fake: Fake = { orders: seed(), writes: [] };
  await page.context().addCookies([{ name: "csrf_token", value: "e2e-csrf-value", url: "http://localhost:3000" }]);
  await stubEmptyCart(page);
  await page.route(/\/api\/v1\/me$/, (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify(me) }));
  const adminOnly = (route: Route, handler: () => Promise<void>) => (me.role !== "admin" ? route.fulfill(problem(404, "NOT_FOUND")) : handler());

  await page.route(/\/api\/v1\/admin\/orders(\?.*)?$/, (route) =>
    adminOnly(route, async () => {
      const url = new URL(route.request().url());
      let items = [...fake.orders].sort((a, b) => String(b.placed_at).localeCompare(String(a.placed_at)));
      const status = url.searchParams.get("status");
      const payment = url.searchParams.get("payment_method");
      const due = url.searchParams.get("payment_due");
      const number = url.searchParams.get("order_number");
      if (status) items = items.filter((o) => o.status === status);
      if (payment) items = items.filter((o) => o.payment_method === payment);
      if (due) items = items.filter((o) => String(o.payment_due) === due);
      if (number) items = items.filter((o) => o.order_number === number);
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: items.map(summary), next_cursor: null }) });
    })
  );
  await page.route(/\/api\/v1\/admin\/orders\/[^/?]+$/, (route) =>
    adminOnly(route, async () => {
      const id = new URL(route.request().url()).pathname.split("/").pop();
      const o = fake.orders.find((x) => x.id === id);
      await route.fulfill(o ? { contentType: "application/json", body: JSON.stringify(view(o)) } : problem(404, "NOT_FOUND"));
    })
  );
  await page.route(/\/api\/v1\/admin\/orders\/[^/]+\/(items\/[^/]+\/transition|cash-handover|cancel)$/, (route) =>
    adminOnly(route, async () => {
      const req = route.request();
      const path = new URL(req.url()).pathname;
      const body = req.postData() ? (JSON.parse(req.postData()!) as Json) : null;
      const csrf = req.headers()["x-csrf-token"] ?? null;
      fake.writes.push({ path, body, csrf });
      if (csrf !== "e2e-csrf-value") return route.fulfill(problem(403, "CSRF_INVALID"));
      const parts = path.split("/");
      const o = fake.orders.find((x) => x.id === parts[5]);
      if (!o) return route.fulfill(problem(404, "NOT_FOUND"));
      const lines = o.lines as Json[];
      const history = o.status_history as Json[];
      if (path.endsWith("/transition")) {
        const l = lines.find((x) => x.id === parts[7]);
        if (!l) return route.fulfill(problem(404, "NOT_FOUND"));
        const target = String(body?.target_status);
        const allowed = actionsFor(o, l).find((a) => a.target_status === target) as Json | undefined;
        if (!allowed) {
          const reason = l.product_type === "stl" && l.fulfillment_status === "delivered" ? "already_delivered" : o.payment_method === "cash" && target === "delivered" ? "cash_handover_required" : "not_a_legal_edge";
          return route.fulfill(problem(409, "INVALID_STATE_TRANSITION", { reason, fulfillment_status: l.fulfillment_status }));
        }
        if ((allowed.cancel_reasons as string[]).length > 0 && !body?.cancel_reason) return route.fulfill(problem(409, "INVALID_STATE_TRANSITION", { reason: "cancel_reason_required" }));
        history.push({ order_item_id: l.id, from_status: l.fulfillment_status, to_status: target, actor_user_id: "admin-1", reason: body?.reason ?? null, at: NOW });
        l.fulfillment_status = target;
        if (target === "cancelled") Object.assign(l, { cancelled_at: NOW, cancel_reason: body?.cancel_reason ?? null });
        if (l.product_type === "stl" && target === "delivered") Object.assign(l, { fulfilled_at: NOW, delivered_by: "admin-1" });
      } else if (path.endsWith("/cash-handover")) {
        const live = lines.filter((x) => x.fulfillment_status !== "cancelled");
        if (o.payment_method !== "cash") return route.fulfill(problem(409, "INVALID_STATE_TRANSITION", { reason: "not_a_cash_order" }));
        if (!live.every((x) => x.fulfillment_status === "shipped")) return route.fulfill(problem(409, "INVALID_STATE_TRANSITION", { reason: "lines_not_ready" }));
        const dueCents = (o.amount_due as { amount_cents: number }).amount_cents;
        if (body?.amount_cents !== dueCents) return route.fulfill(problem(422, "CASH_AMOUNT_MISMATCH", { amount_due: usd(dueCents) }));
        for (const x of live) {
          history.push({ order_item_id: x.id, from_status: "shipped", to_status: "delivered", actor_user_id: "admin-1", reason: null, at: NOW });
          x.fulfillment_status = "delivered";
        }
        (o.payments as Json[]).unshift({ id: "cash-1", provider: "cash", status: "paid", amount: usd(dueCents), initiated_at: NOW, verified_at: NOW, late_captured_at: null, recorded_by: "admin-1" });
        Object.assign(o, { payment_due: false, amount_due: null, payment_reached_paid: true });
      } else {
        if (!String(body?.reason ?? "").trim()) return route.fulfill(problem(422, "VALIDATION_ERROR"));
        for (const x of lines) {
          if (x.product_type === "physical" && ["pending", "in_production", "ready_to_ship"].includes(String(x.fulfillment_status))) {
            history.push({ order_item_id: x.id, from_status: x.fulfillment_status, to_status: "cancelled", actor_user_id: "admin-1", reason: body?.reason ?? null, at: NOW });
            Object.assign(x, { fulfillment_status: "cancelled", cancelled_at: NOW });
          }
        }
      }
      recompute(o);
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(view(o)) });
    })
  );
  await page.route(/\/api\/v1\/admin\/stl-deliveries(\?.*)?$/, (route) =>
    adminOnly(route, async () => {
      const items = fake.orders.flatMap((o) =>
        (o.lines as Json[])
          .filter((l) => l.product_type === "stl" && l.fulfillment_status === "awaiting_delivery")
          .map((l) => ({ item_id: l.id, order_id: o.id, order_number: o.order_number, product_id: l.product_id, product_name: l.name, customer_id: o.customer_id, customer_email: o.customer_email, line_total_cents: 900, currency: "USD", queued_at: o.placed_at }))
      );
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ items, next_cursor: null }) });
    })
  );
  return fake;
}

const items = (page: Page) => page.getByRole("region", { name: "Items" });

test.describe("Admin orders + fulfillment (Phase 5H / FVS-030)", () => {
  test("a customer gets the real 404 for the admin order screens", async ({ page }) => {
    await install(page, CUSTOMER_ME);
    await page.goto(`/admin/orders/${CASH_ID}`);
    await expect(page.getByText(/404/)).toBeVisible();
    // No admin order content leaks into the page body. Scoped to <main>: the
    // static storefront footer copy ("made to order", Batch 2) is not data.
    expect((await page.getByRole("main").innerText()).toLowerCase()).not.toContain("order");
  });

  test("queue: nav entry, server rows, filters sent to the backend", async ({ page }) => {
    await install(page);
    await page.goto("/admin/settings").catch(() => undefined);
    await page.route(/\/api\/v1\/admin\/settings(\?.*)?$/, (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [], next_cursor: null }) }));
    await page.goto("/admin/orders");
    await expect(page.getByRole("navigation", { name: "Admin" }).getByRole("link", { name: "Orders" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("link", { name: /^B3D-/ })).toHaveText(["B3D-CASH0001", "B3D-ONLN0002", "B3D-STL00003"]);
    await page.getByLabel("Cash due").selectOption("true");
    await expect(page.getByRole("link", { name: /^B3D-/ })).toHaveText(["B3D-CASH0001"]);
    await page.getByLabel("Cash due").selectOption("");
    await page.getByLabel("Payment").selectOption("online");
    await expect(page.getByRole("link", { name: /^B3D-/ })).toHaveText(["B3D-ONLN0002", "B3D-STL00003"]);
  });

  test("physical fulfillment through the server's actions, then cash handover; persists on reload", async ({ page }) => {
    const fake = await install(page);
    await page.goto(`/admin/orders/${CASH_ID}`);
    await expect(page.getByRole("button", { name: "Record cash handover" })).toHaveCount(0);

    for (const [button, status] of [["Start production", "In production"], ["Mark ready to ship", "Ready to ship"], ["Mark shipped", "Shipped"]] as const) {
      await items(page).getByRole("button", { name: button }).click();
      const dialog = page.getByRole("dialog", { name: `${button}?` });
      await dialog.getByRole("button", { name: button }).click();
      await expect(dialog).toBeHidden();
      await expect(items(page)).toContainText(status);
    }
    // A cash line never offers "Mark delivered": that's the handover.
    await expect(items(page).getByRole("button", { name: "Mark delivered" })).toHaveCount(0);

    await page.getByRole("button", { name: "Record cash handover" }).click();
    const dialog = page.getByRole("dialog", { name: "Record cash handover?" });
    await dialog.getByLabel(/Cash received/).fill("30");
    await dialog.getByRole("button", { name: "Record cash handover" }).click();
    await expect(dialog.getByRole("alert")).toContainText("must be exactly the amount due ($36.00)");
    await dialog.getByLabel(/Cash received/).fill("36");
    await dialog.getByRole("button", { name: "Record cash handover" }).click();
    await expect(dialog).toBeHidden();
    await expect(items(page)).toContainText("Delivered");
    await expect(page.getByRole("heading", { level: 1 }).locator("..")).toContainText("Completed");
    await expect(page.getByRole("region", { name: "Payment" })).toContainText("Cash");

    const handover = fake.writes.filter((w) => w.path.endsWith("/cash-handover"));
    expect(handover.map((w) => w.body)).toEqual([{ amount_cents: 3000, currency: "USD" }, { amount_cents: 3600, currency: "USD" }]);
    expect(fake.writes.every((w) => w.csrf === "e2e-csrf-value")).toBe(true);

    await page.reload();
    await expect(items(page)).toContainText("Delivered");
    await expect(page.getByRole("region", { name: "History" })).toContainText("Staff");
  });

  test("an illegal transition (stale page) shows safe copy and re-reads", async ({ page }) => {
    const fake = await install(page);
    await page.goto(`/admin/orders/${CASH_ID}`);
    await items(page).getByRole("button", { name: "Start production" }).waitFor();
    // Someone else moved the line meanwhile.
    ((fake.orders[0]!.lines as Json[])[0]!).fulfillment_status = "cancelled";
    await items(page).getByRole("button", { name: "Start production" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "Start production" }).click();
    await expect(dialog.getByRole("alert")).toContainText("That step isn't allowed from the line's current state.");
    await expect(dialog).not.toContainText("RAW");
    await dialog.getByRole("button", { name: "Back" }).click();
    await expect(items(page)).toContainText("Cancelled");
    await expect(items(page).getByRole("button")).toHaveCount(0);
  });

  test("online paid line: Mark delivered is offered and completes the order", async ({ page }) => {
    await install(page);
    await page.goto(`/admin/orders/${ONLINE_ID}`);
    await items(page).getByRole("button", { name: "Mark delivered" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Mark delivered" }).click();
    await expect(page.getByRole("heading", { level: 1 }).locator("..")).toContainText("Completed");
  });

  test("STL manual delivery: queue -> Mark emailed; the line reads Sent by email; no upload or download", async ({ page }) => {
    const fake = await install(page);
    await page.goto("/admin/stl-deliveries");
    await expect(page.getByText("Dragon STL")).toBeVisible();
    await expect(page.getByText(/download|upload/i)).toHaveCount(0);
    await page.getByRole("button", { name: "Mark emailed" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Mark emailed" }).click();
    await expect(page.getByText("No STL files are waiting to be emailed.")).toBeVisible();
    expect(fake.writes.at(-1)).toEqual(expect.objectContaining({ path: `/api/v1/admin/orders/${STL_ORDER_ID}/items/${STL_LINE_ID}/transition`, body: { target_status: "delivered" } }));
    await page.goto(`/admin/orders/${STL_ORDER_ID}`);
    await expect(items(page)).toContainText("Sent by email");
    await expect(items(page).getByRole("button")).toHaveCount(0);
  });

  test("cancel order requires a reason; CSRF failure is safe", async ({ page }) => {
    const fake = await install(page);
    await page.goto(`/admin/orders/${CASH_ID}`);
    await page.getByRole("region", { name: "Order actions" }).getByRole("button", { name: "Cancel order" }).click();
    const dialog = page.getByRole("dialog", { name: "Cancel this order?" });
    await dialog.getByRole("button", { name: "Cancel order" }).click();
    await expect(dialog).toContainText("Enter a reason for cancelling.");
    expect(fake.writes).toHaveLength(0);
    await dialog.getByLabel(/Why is this order being cancelled/).fill("Out of filament");
    await page.context().addCookies([{ name: "csrf_token", value: "stale", url: "http://localhost:3000" }]);
    await dialog.getByRole("button", { name: "Cancel order" }).click();
    await expect(dialog.getByRole("alert")).toContainText("Unable to verify your session");
    await page.context().addCookies([{ name: "csrf_token", value: "e2e-csrf-value", url: "http://localhost:3000" }]);
    await dialog.getByRole("button", { name: "Cancel order" }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByRole("heading", { level: 1 }).locator("..")).toContainText("Cancelled");
  });

  test("keyboard and mobile: the action dialog is reachable and fits", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 740 });
    await install(page);
    await page.goto(`/admin/orders/${CASH_ID}`);
    const start = items(page).getByRole("button", { name: "Start production" });
    await start.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog")).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(start).toBeFocused();
  });
});
