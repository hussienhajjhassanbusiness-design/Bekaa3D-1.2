import { test, expect, type Page, type Route } from "@playwright/test";
import { stubEmptyCart } from "./support/stubCart";
import { E2E_ORIGIN } from "./support/origin";

// Phase 5G — FVS-031 customer order actions on /account/orders/[id] against
// a deterministic, stateful in-memory stand-in for backend 2dfb27b
// (ordering/api/cancel.py, ordering/api/receipt.py). Route interception
// only: no backend on :8000, no media server on :8001 (lines have no image).
//
// The fake applies the documented rules:
//   cancel           409 ORDER_NOT_CANCELLABLE unless can_cancel; on success
//                    the physical pending lines become `cancelled`, the
//                    order recomputes, and status_history gains entries.
//   confirm-receipt  409 INVALID_STATE_TRANSITION { reason:
//                    "no_delivered_line" } without a delivered/picked-up
//                    physical line; stamps receipt_confirmed_at once.
//   report-problem   same 409; 422 on a blank message; 201 + detail.
// Every POST requires the X-CSRF-Token header (403 CSRF_INVALID otherwise)
// and answers with the full OrderDetailRead.
//
// Route patterns are exact: `/api/v1/me`, `/api/v1/me/orders`,
// `/api/v1/me/orders/{id}`, `/api/v1/me/orders/{id}/{action}`.

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

const CASH_ID = uuid(11);
const STL_ID = uuid(12);
const DELIVERED_ID = uuid(13);
const SHIPPED_ID = uuid(14);
const STARTED_ID = uuid(15);

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

function order(id: string, number: string, overrides: Json = {}): Json {
  return {
    id,
    order_number: number,
    source: "cart",
    status: "in_progress",
    fulfillment_method: "delivery",
    payment_method: "cash",
    payment_due: true,
    amount_due: usd(3600),
    can_cancel: false,
    can_retry_payment: false,
    hold_expires_at: null,
    subtotal: usd(3600),
    tax: usd(0),
    total: usd(3600),
    delivery_address: { recipient_name: "Ada Lovelace", governorate: "beqaa", city: "Zahle", area: null, street: "Main St", landmark_notes: null },
    contact_phone: "+96170123456",
    delivery_fee_note: "The delivery fee is paid to the courier on delivery.",
    estimated_dispatch_at: null,
    placed_at: "2026-11-11T10:00:00Z",
    completed_at: null,
    cancelled_at: null,
    customer_note: null,
    lines: [line()],
    payment: null,
    status_history: [{ order_item_id: null, from_status: null, to_status: "in_progress", at: "2026-11-11T10:00:00Z" }],
    refunds: [],
    ...overrides,
  };
}

function seed(): Json[] {
  return [
    order(CASH_ID, "B3D-2026-000011", { can_cancel: true }),
    order(STL_ID, "B3D-2026-000012", {
      fulfillment_method: null,
      payment_method: "online",
      payment_due: false,
      amount_due: null,
      delivery_address: null,
      contact_phone: null,
      delivery_fee_note: null,
      lines: [line({ id: "l-stl", product_type: "stl", name: "Dragon STL", quantity: 1, fulfillment_status: "awaiting_delivery" })],
      payment: { status: "paid", provider: "mock", amount: usd(900) },
    }),
    order(DELIVERED_ID, "B3D-2026-000013", { lines: [line({ fulfillment_status: "delivered" })] }),
    // Shipped, not yet delivered: confirm/report are not offered; a stale
    // page that still offers them gets the server's no_delivered_line.
    order(SHIPPED_ID, "B3D-2026-000014", { lines: [line({ fulfillment_status: "shipped" })] }),
    // The page loaded while can_cancel was true; printing has since started.
    order(STARTED_ID, "B3D-2026-000015", { can_cancel: true }),
  ];
}

const STARTED_REFUSES = new Set([STARTED_ID]);

function problem(status: number, code: string, extra: Json = {}) {
  return {
    status,
    contentType: "application/problem+json",
    body: JSON.stringify({ type: "about:blank", title: "RAW TITLE", status, detail: "RAW DETAIL", code, errors: [], ...extra }),
  };
}

interface Fake {
  orders: Json[];
  posts: { action: string; body: string | null; csrf: string | null }[];
  // Fail the next N calls of an action with this response.
  failNext: Map<string, ReturnType<typeof problem>[]>;
}

const NOW = "2026-11-12T09:00:00Z";
const RECEIVED = new Set(["delivered", "picked_up"]);

function apply(fake: Fake, o: Json, action: string, body: Json | null): ReturnType<typeof problem> | null {
  const lines = o.lines as Json[];
  const history = o.status_history as Json[];
  if (action === "cancel") {
    if (!o.can_cancel || STARTED_REFUSES.has(String(o.id))) return problem(409, "ORDER_NOT_CANCELLABLE");
    for (const l of lines) {
      if (l.product_type === "physical" && l.fulfillment_status === "pending") {
        history.push({ order_item_id: l.id, from_status: "pending", to_status: "cancelled", at: NOW });
        l.fulfillment_status = "cancelled";
        l.cancelled_at = NOW;
      }
    }
    history.push({ order_item_id: null, from_status: o.status, to_status: "cancelled", at: NOW });
    Object.assign(o, { status: "cancelled", cancelled_at: NOW, can_cancel: false, payment_due: false, amount_due: null });
    return null;
  }
  const received = lines.filter((l) => l.product_type === "physical" && RECEIVED.has(String(l.fulfillment_status)));
  if (action === "report-problem") {
    const message = typeof body?.message === "string" ? body.message : "";
    if (message.trim() === "" || Object.keys(body ?? {}).some((k) => k !== "message")) return problem(422, "VALIDATION_ERROR");
  }
  if (received.length === 0) return problem(409, "INVALID_STATE_TRANSITION", { reason: "no_delivered_line" });
  const field = action === "confirm-receipt" ? "receipt_confirmed_at" : "problem_reported_at";
  for (const l of received) if (l[field] === null) l[field] = NOW;
  void fake;
  return null;
}

async function installFakeBackend(page: Page, options: { overrides?: Record<string, Json> } = {}): Promise<Fake> {
  const fake: Fake = { orders: seed(), posts: [], failNext: new Map() };
  for (const [id, patch] of Object.entries(options.overrides ?? {})) {
    Object.assign(fake.orders.find((o) => o.id === id)!, patch);
  }

  await page.context().addCookies([{ name: "csrf_token", value: "e2e-csrf-value", url: E2E_ORIGIN }]);
  await stubEmptyCart(page);
  await page.route(/\/api\/v1\/me$/, (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(ME) }));
  await page.route(/\/api\/v1\/settings\/public$/, (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(SETTINGS) })
  );
  await page.route(/\/api\/v1\/me\/orders(\?.*)?$/, (route) => {
    const keys = ["id", "order_number", "status", "payment_method", "fulfillment_method", "payment_due", "amount_due", "total", "placed_at"];
    const items = fake.orders.map((o) => Object.fromEntries(keys.map((k) => [k, o[k]])));
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ items, next_cursor: null }) });
  });
  await page.route(/\/api\/v1\/me\/orders\/[^/?]+$/, (route) => {
    const id = decodeURIComponent(new URL(route.request().url()).pathname.split("/").pop() ?? "");
    const o = fake.orders.find((x) => x.id === id);
    return route.fulfill(o ? { contentType: "application/json", body: JSON.stringify(o) } : problem(404, "NOT_FOUND"));
  });
  await page.route(/\/api\/v1\/me\/orders\/[^/?]+\/(cancel|confirm-receipt|report-problem)$/, (route: Route) => {
    const request = route.request();
    if (request.method() !== "POST") return route.fallback();
    const parts = new URL(request.url()).pathname.split("/");
    const action = parts.pop() ?? "";
    const id = decodeURIComponent(parts.pop() ?? "");
    const raw = request.postData();
    const csrf = request.headers()["x-csrf-token"] ?? null;
    fake.posts.push({ action, body: raw, csrf });
    if (csrf !== "e2e-csrf-value") return route.fulfill(problem(403, "CSRF_INVALID"));
    const queued = fake.failNext.get(action);
    if (queued && queued.length > 0) return route.fulfill(queued.shift()!);
    const o = fake.orders.find((x) => x.id === id);
    if (!o) return route.fulfill(problem(404, "NOT_FOUND"));
    const refusal = apply(fake, o, action, raw ? (JSON.parse(raw) as Json) : null);
    if (refusal) return route.fulfill(refusal);
    return route.fulfill({
      status: action === "report-problem" ? 201 : 200,
      contentType: "application/json",
      body: JSON.stringify(o),
    });
  });
  return fake;
}

const actions = (page: Page) => page.getByRole("region", { name: "Order actions" });

async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

test.describe("Customer order actions (Phase 5G / FVS-031)", () => {
  test("cancellable cash order: confirm, cancel once, server status + history after refetch, persists on reload", async ({ page }) => {
    const fake = await installFakeBackend(page);
    await page.goto(`/account/orders/${CASH_ID}`);
    await actions(page).getByRole("button", { name: "Cancel order" }).click();

    const dialog = page.getByRole("dialog", { name: "Cancel this order?" });
    await expect(dialog).toContainText("won't need to pay for the cancelled items");
    await expect(dialog.getByRole("button", { name: "Keep my order" })).toBeFocused();
    await dialog.getByRole("button", { name: "Cancel order" }).dblclick();

    await expect(dialog).toBeHidden();
    await expect(actions(page).getByRole("status")).toContainText("Your cancellation went through");
    const posts = fake.posts.filter((p) => p.action === "cancel");
    expect(posts).toHaveLength(1);
    expect(posts[0]!.body).toBeNull();
    expect(posts[0]!.csrf).toBe("e2e-csrf-value");

    await expect(page.getByRole("heading", { level: 1 }).locator("..")).toContainText("Cancelled");
    await expect(page.getByRole("region", { name: "Order updates" })).toContainText("Order: Cancelled");
    await expect(actions(page).getByRole("button", { name: "Cancel order" })).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Summary" })).not.toContainText("Amount due");

    await page.reload();
    await expect(page.getByRole("heading", { level: 1 }).locator("..")).toContainText("Cancelled");
    await expect(page.getByRole("button", { name: "Cancel order" })).toHaveCount(0);
  });

  test("refused cancel (printing started): dialog stays open with safe copy; the page re-reads the server state", async ({ page }) => {
    const fake = await installFakeBackend(page);
    await page.goto(`/account/orders/${STARTED_ID}`);
    await actions(page).getByRole("button", { name: "Cancel order" }).click();
    await expect(page.getByRole("dialog", { name: "Cancel this order?" })).toBeVisible();
    // The server now reports can_cancel false (the refetch after refusal shows it).
    Object.assign(fake.orders.find((o) => o.id === STARTED_ID)!, { can_cancel: false });
    const dialog = page.getByRole("dialog", { name: "Cancel this order?" });
    await dialog.getByRole("button", { name: "Cancel order" }).click();
    await expect(dialog.getByRole("alert")).toContainText("can no longer be cancelled");
    await expect(dialog).not.toContainText("RAW");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Keep my order" }).click();
    await expect(page.getByRole("button", { name: "Cancel order" })).toHaveCount(0);
  });

  test("STL-only order: no cancellation offered (server can_cancel false)", async ({ page }) => {
    await installFakeBackend(page);
    await page.goto(`/account/orders/${STL_ID}`);
    await expect(page.getByRole("heading", { level: 1, name: "Order B3D-2026-000012" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Cancel order" })).toHaveCount(0);
    await expect(actions(page)).toHaveCount(0);
  });

  test("a missing CSRF header is refused with safe copy (CSRF_INVALID)", async ({ page }) => {
    await installFakeBackend(page);
    await page.goto(`/account/orders/${CASH_ID}`);
    // Rotate the cookie so the header no longer matches what the fake expects.
    await page.context().addCookies([{ name: "csrf_token", value: "stale", url: E2E_ORIGIN }]);
    await actions(page).getByRole("button", { name: "Cancel order" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "Cancel order" }).click();
    await expect(dialog.getByRole("alert")).toContainText("Unable to verify your session");
  });

  test("confirm receipt: one POST, the server's timestamp is shown, the action is no longer offered", async ({ page }) => {
    const fake = await installFakeBackend(page);
    await page.goto(`/account/orders/${DELIVERED_ID}`);
    await actions(page).getByRole("button", { name: "I received my items" }).click();
    await expect(actions(page).getByRole("status")).toContainText("We've recorded that you received your items");
    await expect(actions(page)).toContainText("You confirmed you received your items on 12 November 2026");
    await expect(actions(page).getByRole("button", { name: "I received my items" })).toHaveCount(0);
    expect(fake.posts.filter((p) => p.action === "confirm-receipt")).toHaveLength(1);
    await page.reload();
    await expect(actions(page)).toContainText("You confirmed you received your items on 12 November 2026");
  });

  test("confirm receipt refused with no_delivered_line: safe copy, no backend text", async ({ page }) => {
    // A stale page: the order was shown as delivered, the server now disagrees.
    const fake = await installFakeBackend(page);
    await page.goto(`/account/orders/${DELIVERED_ID}`);
    await expect(actions(page).getByRole("button", { name: "I received my items" })).toBeVisible();
    const lines = fake.orders.find((o) => o.id === DELIVERED_ID)!.lines as Json[];
    lines[0]!.fulfillment_status = "returned";
    await actions(page).getByRole("button", { name: "I received my items" }).click();
    await expect(actions(page).getByRole("alert")).toContainText("None of the items in this order has been delivered or picked up yet.");
    await expect(page.getByText("RAW DETAIL")).toHaveCount(0);
    // The re-read shows the server's state: nothing left to confirm.
    await expect(page.getByRole("button", { name: "I received my items" })).toHaveCount(0);
  });

  test("shipped (not delivered) order offers neither receipt action", async ({ page }) => {
    await installFakeBackend(page);
    await page.goto(`/account/orders/${SHIPPED_ID}`);
    await expect(page.getByRole("heading", { level: 1, name: "Order B3D-2026-000014" })).toBeVisible();
    await expect(page.getByRole("button", { name: /received my items|report a problem/i })).toHaveCount(0);
  });

  test("report a problem with the keyboard: validation, a server error keeps the text, retry succeeds", async ({ page }) => {
    const fake = await installFakeBackend(page);
    fake.failNext.set("report-problem", [problem(500, "INTERNAL_ERROR")]);
    await page.goto(`/account/orders/${DELIVERED_ID}`);

    await actions(page).getByRole("button", { name: "Report a problem" }).focus();
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "Report a problem" });
    const field = dialog.getByLabel("What's the problem?");
    await expect(field).toBeFocused();

    // Blank: client validation, no request.
    await dialog.getByRole("button", { name: "Send report" }).click();
    await expect(dialog).toContainText("Describe the problem before sending.");
    expect(fake.posts.filter((p) => p.action === "report-problem")).toHaveLength(0);

    await field.fill("The dragon's tail arrived snapped.");
    await dialog.getByRole("button", { name: "Send report" }).click();
    await expect(dialog.getByRole("alert")).toContainText("couldn't confirm whether that went through");
    await expect(field).toHaveValue("The dragon's tail arrived snapped.");

    await dialog.getByRole("button", { name: "Send report" }).click();
    await expect(dialog).toBeHidden();
    await expect(actions(page).getByRole("status")).toContainText("Your report was sent");
    await expect(actions(page)).toContainText("You reported a problem on 12 November 2026");
    const sent = fake.posts.filter((p) => p.action === "report-problem");
    expect(sent).toHaveLength(2);
    expect(JSON.parse(sent[1]!.body!)).toEqual({ message: "The dragon's tail arrived snapped." });

    await page.reload();
    await expect(actions(page)).toContainText("You reported a problem on 12 November 2026");
    // Repeat reports are allowed by the contract.
    await expect(actions(page).getByRole("button", { name: "Report a problem" })).toBeVisible();
  });

  test("Escape closes the report dialog and returns focus to its trigger", async ({ page }) => {
    await installFakeBackend(page);
    await page.goto(`/account/orders/${DELIVERED_ID}`);
    const trigger = actions(page).getByRole("button", { name: "Report a problem" });
    await trigger.click();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("mobile width: actions and dialogs fit without horizontal scroll", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 740 });
    await installFakeBackend(page);
    await page.goto(`/account/orders/${DELIVERED_ID}`);
    await expect(actions(page).getByRole("button", { name: "I received my items" })).toBeVisible();
    await noHorizontalScroll(page);
    await actions(page).getByRole("button", { name: "Report a problem" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await noHorizontalScroll(page);
  });
});
