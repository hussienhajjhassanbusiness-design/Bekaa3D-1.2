import { test, expect, type Page } from "@playwright/test";
import { stubEmptyCart } from "./support/stubCart";
import { E2E_ORIGIN } from "./support/origin";

// Redesign Batch 7 — Orders, order detail, Offers, Wishlist and the
// checkout return page at the six QA widths, against mocked real-shaped
// data (route interception only; no backend). Asserts user-facing intent:
// one h1, no horizontal overflow, the status pill in the h1's parent on
// detail pages, long order numbers / addresses / product names / history
// wrap, actions stay inside their cards at practical sizes, the cancel
// dialog fits a 320px viewport, and the return page stays neutral.

const WIDTHS = [320, 375, 768, 1024, 1280, 1440];
const usd = (amount_cents: number) => ({ amount_cents, currency: "USD" });
const uuid = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
type Json = Record<string, unknown>;

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
  cash_max_order_total: usd(10000),
  pickup_address: "Bekaa3D workshop, Zahle",
  pickup_hours: "Mon-Fri 10:00-18:00",
  whatsapp_number: null,
};

const LONG_NAME = "Articulated Planetary Gearbox Display Model with Interchangeable Sun, Planet and Ring Gears";
const CASH_ID = uuid(1);
const REFUNDED_ID = uuid(2);

function line(overrides: Json = {}): Json {
  return {
    id: "l-phys",
    product_id: "p-1",
    product_type: "physical",
    name: LONG_NAME,
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

const ADDRESS = {
  recipient_name: "Marie-Thérèse Abou Khalil El Haddad",
  governorate: "keserwan_jbeil",
  city: "Jounieh",
  area: "Sahel Alma, near the Notre-Dame du Liban funicular",
  street: "Rue Mar Elias, Building Khoury-Sfeir, third floor",
  landmark_notes: "Blue gate next to the bakery, opposite the pharmacy; ring twice and call on arrival.",
};

function detail(overrides: Json): Json {
  return {
    source: "cart",
    can_cancel: false,
    can_retry_payment: false,
    hold_expires_at: null,
    tax: usd(0),
    delivery_address: ADDRESS,
    contact_phone: "+96170123456",
    delivery_fee_note: "The delivery fee is paid to the courier on delivery.",
    estimated_dispatch_at: "2026-11-14T10:00:00Z",
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
    placed_at: "2026-11-11T10:00:00Z",
    customer_note: "Please call first. The building intercom is broken, so ring the mobile number twice.",
    lines: [line()],
    status_history: [{ order_item_id: null, from_status: null, to_status: "in_progress", at: "2026-11-11T10:00:00Z" }],
  }),
  detail({
    id: REFUNDED_ID,
    order_number: "B3D-2026-000002",
    status: "partially_refunded",
    fulfillment_method: "delivery",
    payment_method: "online",
    payment_due: false,
    amount_due: null,
    subtotal: usd(4500),
    total: usd(4500),
    placed_at: "2026-11-09T10:00:00Z",
    lines: [
      line({ fulfillment_status: "delivered", receipt_confirmed_at: "2026-11-12T10:00:00Z" }),
      line({
        id: "l-c",
        name: "Cedar Planter",
        fulfillment_status: "cancelled",
        cancelled_at: "2026-11-10T10:00:00Z",
        line_total: usd(900),
        unit_price: usd(900),
        quantity: 1,
      }),
      line({
        id: "l-stl",
        product_type: "stl",
        name: "Dragon STL",
        fulfillment_status: "delivered",
        fulfilled_at: "2026-11-09T15:00:00Z",
        line_total: usd(0),
        quantity: 1,
      }),
    ],
    payment: { status: "partially_refunded", provider: "mock", amount: usd(4500) },
    refunds: [{ kind: "cancellation", status: "refunded", amount: usd(900), created_at: "2026-11-10T11:00:00Z" }],
    status_history: Array.from({ length: 8 }, (_, i) => ({
      order_item_id: i % 2 ? "l-phys" : null,
      from_status: null,
      to_status: i % 2 ? "shipped" : "in_progress",
      at: `2026-11-${String(9 + Math.floor(i / 2)).padStart(2, "0")}T1${i}:00:00Z`,
    })),
  }),
];

function summaryOf(order: Json): Json {
  const keys = [
    "id",
    "order_number",
    "status",
    "payment_method",
    "fulfillment_method",
    "payment_due",
    "amount_due",
    "total",
    "placed_at",
  ];
  return Object.fromEntries(keys.map((k) => [k, order[k]]));
}

const OFFER_ID = uuid(50);
const OFFER = {
  id: OFFER_ID,
  product: { id: "p-stl", name: LONG_NAME, slug: "gearbox-stl", cover_image: null },
  status: "awaiting_customer",
  turn: "customer",
  current_amount: usd(1800),
  agreed_amount: null,
  responds_by: "2026-11-16T10:00:00Z",
  checkout_expires_at: null,
  created_at: "2026-11-12T10:00:00Z",
  initial_amount: usd(1500),
  cooldown_until: null,
  updated_at: "2026-11-12T11:00:00Z",
  rounds: [
    {
      sequence: 1,
      actor: "customer",
      action: "submitted",
      amount: usd(1500),
      message: "Would you take $15?",
      created_at: "2026-11-12T10:00:00Z",
    },
    {
      sequence: 2,
      actor: "admin",
      action: "countered",
      amount: usd(1800),
      message: "We can do $18 given the print-in-place tolerances and the extra support work this model needs.",
      created_at: "2026-11-12T11:00:00Z",
    },
  ],
  allowed_actions: ["accept", "counter", "withdraw"],
};

const OFFER_SUMMARY = {
  id: OFFER.id,
  product: OFFER.product,
  status: OFFER.status,
  turn: OFFER.turn,
  current_amount: OFFER.current_amount,
  agreed_amount: OFFER.agreed_amount,
  responds_by: OFFER.responds_by,
  checkout_expires_at: OFFER.checkout_expires_at,
  created_at: OFFER.created_at,
};

const WISHLIST = [
  {
    product_id: uuid(70),
    created_at: "2026-11-12T10:00:00Z",
    available: true,
    name: LONG_NAME,
    slug: "gearbox",
    type: "physical",
    price_cents: 4500,
    currency: "USD",
  },
  {
    product_id: uuid(71),
    created_at: "2026-11-11T10:00:00Z",
    available: true,
    name: "Dragon STL",
    slug: "dragon-stl",
    type: "stl",
    price_cents: 700,
    currency: "USD",
  },
  {
    product_id: uuid(72),
    created_at: "2026-11-10T10:00:00Z",
    available: false,
    name: "Old vase",
    slug: null,
    type: null,
    price_cents: null,
    currency: null,
  },
];

async function signIn(page: Page) {
  await page.context().addCookies([{ name: "csrf_token", value: "e2e-csrf-value", url: E2E_ORIGIN }]);
  await stubEmptyCart(page);
  const json = (body: unknown) => ({ contentType: "application/json", body: JSON.stringify(body) });
  await page.route(/\/api\/v1\/me$/, (route) => route.fulfill(json(ME)));
  await page.route(/\/api\/v1\/settings\/public$/, (route) => route.fulfill(json(SETTINGS)));
  await page.route(/\/api\/v1\/me\/orders(\?.*)?$/, (route) =>
    route.fulfill(json({ items: ORDERS.map(summaryOf), next_cursor: null }))
  );
  await page.route(/\/api\/v1\/me\/orders\/[^/?]+$/, (route) => {
    const id = decodeURIComponent(new URL(route.request().url()).pathname.split("/").pop() ?? "");
    return route.fulfill(json(ORDERS.find((o) => o.id === id)));
  });
  await page.route(/\/api\/v1\/me\/offers(\?.*)?$/, (route) =>
    route.fulfill(json({ items: [OFFER_SUMMARY], next_cursor: null }))
  );
  await page.route(/\/api\/v1\/me\/offers\/[^/?]+$/, (route) => route.fulfill(json(OFFER)));
  await page.route(/\/api\/v1\/me\/wishlist(\?.*)?$/, (route) =>
    route.fulfill(json({ items: WISHLIST, next_cursor: null }))
  );
}

async function expectNoOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth
  );
  expect(overflow).toBeLessThanOrEqual(0);
}

async function expectInside(inner: ReturnType<Page["locator"]>, outer: ReturnType<Page["locator"]>) {
  const a = (await inner.boundingBox())!;
  const b = (await outer.boundingBox())!;
  expect(a.x).toBeGreaterThanOrEqual(b.x - 0.5);
  expect(a.x + a.width).toBeLessThanOrEqual(b.x + b.width + 0.5);
}

test.describe("Account commerce pages responsive (redesign Batch 7)", () => {
  for (const width of WIDTHS) {
    test(`orders, order detail, offers, wishlist and the return page at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await signIn(page);

      // Orders list
      await page.goto("/account/orders");
      await expect(page.getByRole("heading", { level: 1, name: "Orders" })).toBeVisible();
      await expect(page.getByRole("link", { name: /^Order B3D-/ })).toHaveCount(2);
      const cashRow = page.getByRole("listitem").filter({ hasText: "Order B3D-2026-000001" });
      await expect(cashRow).toContainText("In progress");
      await expect(cashRow).toContainText(/Payment due in cash:\s*\$36\.00/);
      await expect(page.getByRole("listitem").filter({ hasText: "Order B3D-2026-000002" })).toContainText(
        "Partially refunded"
      );
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
      await expectNoOverflow(page);

      // Order detail: partially refunded online order, long address, many updates
      await page.goto(`/account/orders/${REFUNDED_ID}`);
      const h1 = page.getByRole("heading", { level: 1, name: "Order B3D-2026-000002" });
      await expect(h1).toBeVisible();
      await expect(h1.locator("..")).toContainText("Partially refunded");
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
      await expect(
        page.getByRole("region", { name: "Payment" }).getByText("Partially refunded", { exact: true })
      ).toBeVisible();
      await expect(page.getByRole("region", { name: "Refunds" })).toContainText("Cancellation refund · Refunded");
      await expect(page.getByRole("region", { name: "Delivery" })).toContainText(ADDRESS.landmark_notes);
      await expect(page.getByRole("region", { name: "Items" })).toContainText("STL file, sent by email");
      await expect(page.getByRole("region", { name: "Order updates" }).getByRole("listitem")).toHaveCount(8);
      await expect(page.getByRole("link", { name: /download/i })).toHaveCount(0);
      await expectNoOverflow(page);

      // Cash order: cancel dialog fits and keeps the 24-hour cash warning
      await page.goto(`/account/orders/${CASH_ID}`);
      const actions = page.getByRole("region", { name: "Order actions" });
      const cancel = actions.getByRole("button", { name: "Cancel order" });
      await expect(cancel).toBeVisible();
      expect((await cancel.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      await expectInside(cancel, actions);
      await cancel.click();
      const dialog = page.getByRole("dialog", { name: "Cancel this order?" });
      await expect(dialog.getByText(/choose cash payment for a new order for 24 hours/)).toBeVisible();
      await expect(dialog.getByRole("button", { name: "Keep my order" })).toBeFocused();
      const dialogBox = (await dialog.boundingBox())!;
      expect(dialogBox.x).toBeGreaterThanOrEqual(0);
      expect(dialogBox.x + dialogBox.width).toBeLessThanOrEqual(width);
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expectNoOverflow(page);

      // Offers list and detail
      await page.goto("/account/offers");
      await expect(page.getByRole("heading", { level: 1, name: "Offers" })).toBeVisible();
      await expect(page.getByRole("link", { name: `Offer on ${LONG_NAME}` })).toBeVisible();
      await expectNoOverflow(page);
      await page.goto(`/account/offers/${OFFER_ID}`);
      const offerH1 = page.getByRole("heading", { level: 1, name: `Offer on ${LONG_NAME}` });
      await expect(offerH1).toBeVisible();
      await expect(offerH1.locator("..")).toContainText("Your reply needed");
      const reply = page.getByRole("region", { name: "Your reply" });
      await expect(reply.getByRole("button")).toHaveText(["Accept this amount", "Counter-offer", "Withdraw offer"]);
      for (const button of await reply.getByRole("button").all()) {
        expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
        await expectInside(button, reply);
      }
      await expect(page.getByRole("region", { name: "History" }).getByRole("listitem")).toHaveCount(2);
      await expectNoOverflow(page);

      // Wishlist
      await page.goto("/account/wishlist");
      await expect(page.getByRole("heading", { level: 1, name: "Wishlist" })).toBeVisible();
      await expect(page.getByText("Showing 3 items")).toBeVisible();
      const card = page.getByRole("listitem").filter({ hasText: "Dragon STL" });
      const remove = card.getByRole("button", { name: "Remove Dragon STL from your wishlist" });
      const box = (await remove.boundingBox())!;
      expect(box.height).toBeGreaterThanOrEqual(44);
      expect(box.width).toBeGreaterThanOrEqual(44);
      await expectInside(remove, card);
      await expect(page.getByRole("listitem").filter({ hasText: "Old vase" })).toContainText("No longer available");
      await expect(page.getByRole("link", { name: LONG_NAME })).toHaveAttribute("href", "/shop/gearbox");
      await expectNoOverflow(page);

      // Checkout return: neutral
      await page.goto("/checkout/return?order=B3D-2026-000002");
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
      await expect(page.getByRole("status")).toContainText("Your payment hasn't been confirmed yet.");
      await expect(page.getByText(/payment (was )?successful|payment failed|order is paid/i)).toHaveCount(0);
      await expect(page.getByRole("link", { name: "View your orders" })).toBeVisible();
      await expectNoOverflow(page);
    });
  }

  test("keyboard: the order row link and the wishlist remove control show a visible focus ring at 375px", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await signIn(page);
    await page.goto("/account/orders");
    const link = page.getByRole("link", { name: "Order B3D-2026-000001" });
    await link.focus();
    await expect(link).toBeFocused();
    expect(await link.evaluate((el) => getComputedStyle(el).boxShadow)).not.toBe("none");

    await page.goto("/account/wishlist");
    const remove = page.getByRole("button", { name: "Remove Dragon STL from your wishlist" });
    await remove.focus();
    await expect(remove).toBeFocused();
    expect(await remove.evaluate((el) => getComputedStyle(el).boxShadow)).not.toBe("none");
  });
});
