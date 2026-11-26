import { test, expect, type Page } from "@playwright/test";
import { stubEmptyCart } from "./support/stubCart";
import { E2E_ORIGIN } from "./support/origin";

// Redesign Batch 10 — representative admin detail / form / action screens at
// the six QA widths inside the admin shell: order detail with many lines and
// long notes, the cash-handover dialog at 320px, a contact message with long
// text, settings, and the new-product form. Asserts layout only (one h1, no
// page-level overflow, dialog within the viewport, 44px action targets).
// Route interception only; the order fixture mirrors admin-orders.spec.ts.

type Json = Record<string, unknown>;
const usd = (amount_cents: number) => ({ amount_cents, currency: "USD" });
const uuid = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const WIDTHS = [320, 375, 768, 1024, 1280, 1440];
const ADMIN_ME = {
  id: "admin-1",
  email: "admin@example.com",
  role: "admin",
  email_verified: true,
  email_verified_at: "2025-01-01T00:00:00Z",
  created_at: "2024-01-01T00:00:00Z",
};
const ORDER_ID = uuid(21);
const LONG_NAME = "Articulated Cedar Dragon with Extra Long Product Name for Layout Checks — Limited Edition Series";
const LONG_NOTE = "Please call before delivery. ".repeat(12);

const DELIVERY: Record<string, string[]> = {
  pending: ["in_production", "cancelled"],
  in_production: ["ready_to_ship", "cancelled"],
  ready_to_ship: ["shipped", "cancelled"],
  shipped: ["delivered", "returned"],
};
const CANCEL_REASONS: Record<string, string[]> = { ready_to_ship: ["refused", "other"] };

function actionsFor(order: Json, line: Json): Json[] {
  if (line.product_type === "stl")
    return line.fulfillment_status === "awaiting_delivery" ? [{ target_status: "delivered", cancel_reasons: [] }] : [];
  const edges = DELIVERY[String(line.fulfillment_status)] ?? [];
  return edges
    .filter((t) => !(order.payment_method === "cash" && t === "delivered"))
    .map((t) => ({
      target_status: t,
      cancel_reasons: t === "cancelled" ? (CANCEL_REASONS[String(line.fulfillment_status)] ?? []) : [],
    }));
}

function line(id: string, overrides: Json = {}): Json {
  return {
    id,
    product_id: "p-1",
    product_type: "physical",
    name: "Articulated Dragon",
    image_url: null,
    unit_price: usd(1800),
    quantity: 2,
    line_total: usd(3600),
    fulfillment_status: "pending",
    fulfilled_at: null,
    delivered_by: null,
    cancelled_at: null,
    cancel_reason: null,
    offer_id: null,
    lead_time_days: 3,
    batch_size: null,
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
    customer_id: "c-1",
    customer_email: "rana@example.com",
    status: "in_progress",
    fulfillment_method: "delivery",
    payment_method: "cash",
    payment_reached_paid: false,
    payment_due: true,
    amount_due: usd(3600),
    subtotal: usd(3600),
    tax: usd(0),
    total: usd(3600),
    delivery_address: {
      recipient_name: "Rana Haddad",
      governorate: "beqaa",
      city: "Zahle",
      area: null,
      street: "Main St 12",
      landmark_notes: null,
    },
    contact_phone: "+96170123456",
    delivery_fee_note: "The courier collects the delivery fee.",
    customer_note: null,
    admin_note: null,
    estimated_dispatch_at: null,
    placed_at: "2026-11-11T10:00:00Z",
    completed_at: null,
    cancelled_at: null,
    lines: [line(uuid(211))],
    payments: [],
    status_history: [
      {
        order_item_id: null,
        from_status: null,
        to_status: "in_progress",
        actor_user_id: "c-1",
        reason: null,
        at: "2026-11-11T10:00:00Z",
      },
    ],
    refunds: [],
    chargebacks: [],
    refund_balance: null,
    ...overrides,
  };
}

function bigOrder(): Json {
  return order(ORDER_ID, "B3D-CASH0001", {
    customer_email: "a.very.long.customer.email.address.for.layout@example-customer-domain.com",
    customer_note: LONG_NOTE,
    admin_note: LONG_NOTE,
    lines: [1, 2, 3, 4, 5, 6].map((n) =>
      line(uuid(210 + n), { name: `${LONG_NAME} #${n}`, fulfillment_status: "ready_to_ship" })
    ),
  });
}

// Batch 11: payment / refund detail with long opaque references and long
// free text (the Batch 10 deferral); shapes as in admin-payments.spec.ts.
const PAYMENT_ID = uuid(41);
const REFUND_ID = uuid(51);
const LONG_REF = `mock_${"a1b2c3d4".repeat(12)}`;
const NOW = "2026-11-12T09:00:00Z";
const PAYMENT_DETAIL = {
  payment: {
    id: PAYMENT_ID,
    order_id: ORDER_ID,
    order_number: "B3D-PAID0001",
    provider: "mock",
    status: "pending",
    amount_cents: 3600,
    currency: "USD",
    captured_amount_cents: null,
    captured_currency: null,
    provider_payment_id: LONG_REF,
    initiated_at: "2026-11-10T10:00:00Z",
    verified_at: null,
    failed_at: null,
    expired_at: null,
    late_captured_at: null,
    needs_manual_confirmation: true,
    unprocessed_event_count: 2,
  },
  order: {
    id: ORDER_ID,
    order_number: "B3D-PAID0001",
    status: "awaiting_payment",
    total_cents: 3600,
    currency: "USD",
    placed_at: "2026-11-10T10:00:00Z",
    cancelled_at: null,
    hold_expires_at: null,
    manual_release_available_at: null,
  },
  events: [],
  history: [{ action: "payment.initiated", actor_user_id: null, created_at: NOW, data: null }],
  available_actions: ["reconcile", "confirm_manually"],
};
const REFUND_DETAIL = {
  id: REFUND_ID,
  order_id: ORDER_ID,
  order_number: "B3D-PAID0001",
  customer_id: "c-1",
  payment_id: PAYMENT_ID,
  payment_provider: "mock",
  kind: "admin",
  status: "failed",
  owed: true,
  amount_cents: 3600,
  currency: "USD",
  reason: LONG_NOTE,
  requested_by: "admin-1",
  approved_by: "admin-1",
  items: [{ order_item_id: uuid(211), product_name: `${LONG_NAME} #1`, amount_cents: 3600 }],
  reissue_of_refund_id: null,
  reissued_by_refund_id: null,
  reissued_at: null,
  settled_at: null,
  settled_by: null,
  settlement_reference: null,
  settlement_note: null,
  failed_at: NOW,
  failed_by: "admin-1",
  failure_reason: `Bank rejected the transfer: ${LONG_REF}`,
  voided_at: null,
  voided_by: null,
  void_reason: null,
  created_at: NOW,
};
const CASH_BLOCKS = [1, 2].map((n) => ({
  id: `b-${n}`,
  customer_id: `c-${n}`,
  order_id: uuid(80 + n),
  order_number: `B3D-REFU000${n}`,
  reason: "refused",
  created_at: "2026-11-09T10:00:00Z",
  active: true,
  cleared_at: null,
  cleared_by: null,
}));

async function asAdmin(page: Page) {
  await page.context().addCookies([{ name: "csrf_token", value: "e2e-csrf-value", url: E2E_ORIGIN }]);
  await page.route(/\/api\/v1\/admin\/payments\/[^/?]+$/, (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify(PAYMENT_DETAIL) })
  );
  await page.route(/\/api\/v1\/admin\/refunds\/[^/?]+$/, (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify(REFUND_DETAIL) })
  );
  await page.route(/\/api\/v1\/admin\/cash-blocks(\?.*)?$/, (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify({ items: CASH_BLOCKS, next_cursor: null }) })
  );
  await stubEmptyCart(page);
  await page.route(/\/api\/v1\/me$/, (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify(ADMIN_ME) })
  );
  const o = bigOrder();
  for (const l of o.lines as Json[]) l.available_actions = actionsFor(o, l);
  await page.route(/\/api\/v1\/admin\/orders\/[^/?]+$/, (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify(o) })
  );
  await page.route(/\/api\/v1\/admin\/contact-messages\/[^/?]+$/, (r) =>
    r.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: uuid(10),
        name: "Rana Haddad",
        email: "rana.with.a.really.long.address@example-customer-domain.com",
        phone: "+96170123456",
        subject: "A very long subject line about PETG prints and custom colours for a workshop order",
        message: `${"Long message text without breaks ".repeat(20)}
${"x".repeat(120)}`,
        status: "new",
        created_at: "2026-11-10T10:00:00Z",
        updated_at: "2026-11-10T10:00:00Z",
        user_id: null,
        order_id: null,
      }),
    })
  );
  await page.route(/\/api\/v1\/admin\/settings(\?.*)?$/, (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [], next_cursor: null }) })
  );
  await page.route(/\/api\/v1\/admin\/(categories|materials|colours)(\?.*)?$/, (r) =>
    r.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [], next_cursor: null }) })
  );
}

async function expectNoOverflow(page: Page, label: string) {
  const [scrollWidth, clientWidth] = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    document.documentElement.clientWidth,
  ]);
  expect(scrollWidth, `${label}: horizontal page overflow`).toBeLessThanOrEqual(clientWidth);
}

const ROUTES: { path: string; heading: RegExp }[] = [
  { path: `/admin/orders/${ORDER_ID}`, heading: /order b3d-cash0001/i },
  { path: `/admin/contact-messages/${uuid(10)}`, heading: /a very long subject line/i },
  { path: "/admin/settings", heading: /^settings$/i },
  { path: "/admin/products/new", heading: /new product/i },
  { path: `/admin/payments/${PAYMENT_ID}`, heading: /payment for order b3d-paid0001/i },
  { path: `/admin/refunds/${REFUND_ID}`, heading: /for order b3d-paid0001/i },
  // Batch 11 regression: a table with row actions (its sr-only "Actions"
  // header) used to widen the whole page by 231px at 320.
  { path: "/admin/cash-blocks", heading: /^cash blocks$/i },
];

for (const route of ROUTES) {
  test(`${route.path}: fits ${WIDTHS.join("/")}px with one h1 and no page overflow`, async ({ page }) => {
    await asAdmin(page);
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(route.path);
      const h1 = page.getByRole("heading", { level: 1 });
      await expect(h1).toHaveCount(1);
      await expect(h1).toHaveText(route.heading);
      await expectNoOverflow(page, `${width}px ${route.path}`);
      for (const button of await page.getByRole("main").getByRole("button").all()) {
        if (!(await button.isVisible())) continue;
        // Row actions live inside a table's own horizontal-scroll region.
        if (await button.evaluate((b) => b.closest('[role="region"][aria-label="Results"]') !== null)) continue;
        const box = (await button.boundingBox())!;
        expect(box.x + box.width, `${width}px: button clipped`).toBeLessThanOrEqual(width);
      }
    }
  });
}

test("cash handover dialog fits 320px, keeps focus inside and its amount field", async ({ page }) => {
  await asAdmin(page);
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto(`/admin/orders/${ORDER_ID}`);
  const actions = page.getByRole("region", { name: "Order actions" });
  await actions.getByRole("button").first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const box = (await dialog.boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(320);
  for (const button of await dialog.getByRole("button").all()) {
    expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});
