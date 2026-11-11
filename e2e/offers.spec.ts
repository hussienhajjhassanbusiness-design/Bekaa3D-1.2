import { test, expect, type Page, type Route } from "@playwright/test";
import { stubEmptyCart } from "./support/stubCart";

// Phase 6C — Offers against a deterministic stand-in for backend 2dfb27b
// (negotiation/api/offers.py, admin_offers.py, ordering/api/offer_checkout.py).
// Route interception only: no backend on :8000, no media server on :8001.
// Exact route patterns; the fake keeps the offer state between requests.

type Json = Record<string, unknown>;
const uuid = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const usd = (amount_cents: number) => ({ amount_cents, currency: "USD" });
const ADMIN_ME = { id: "admin-1", email: "admin@example.com", role: "admin", email_verified: true, email_verified_at: "2025-01-01T00:00:00Z", created_at: "2024-01-01T00:00:00Z" };
const CUSTOMER_ME = { ...ADMIN_ME, id: uuid(901), email: "rana@example.com", role: "customer" };
const PRODUCT_ID = uuid(501);
const OFFER_ID = uuid(601);
const ORDER_ID = uuid(701);

const STL_DETAIL = {
  id: PRODUCT_ID,
  type: "stl",
  name: "Dragon STL",
  slug: "dragon-stl",
  cover_image: null,
  price: usd(2000),
  category: { id: "c1", name: "Toys and Figures", slug: "toys-figures" },
  material: null,
  colour: null,
  is_available: true,
  purchase_mode: null,
  average_rating: 0,
  review_count: 0,
  is_featured: false,
  description: "A dragon you print yourself.",
  images: [],
  seo_title: null,
  seo_description: null,
  og_image_url: null,
  dimensions: null,
  production_lead_time_days: null,
  batch_size: null,
  max_quantity_per_line: null,
  capabilities: { can_add_to_cart: true, can_offer: true, whatsapp_available: false },
};

function problem(status: number, code: string, extra: Json = {}) {
  return { status, contentType: "application/problem+json", body: JSON.stringify({ type: "about:blank", title: "RAW TITLE", status, detail: "RAW DETAIL", code, errors: [], ...extra }) };
}

interface Write {
  path: string;
  body: unknown;
  csrf: string | null;
  key: string | null;
}

interface Fake {
  offer: Json | null;
  writes: Write[];
  failNext: Map<string, ReturnType<typeof problem>>;
}

function baseOffer(): Json {
  return {
    id: OFFER_ID,
    product: { id: PRODUCT_ID, name: "Dragon STL", slug: "dragon-stl", cover_image: null },
    status: "awaiting_admin",
    turn: "admin",
    current_amount: usd(1500),
    agreed_amount: null,
    responds_by: "2026-11-20T10:00:00Z",
    checkout_expires_at: null,
    created_at: "2026-11-12T10:00:00Z",
    initial_amount: usd(1500),
    cooldown_until: null,
    updated_at: "2026-11-12T10:00:00Z",
    rounds: [{ sequence: 1, actor: "customer", action: "submitted", amount: usd(1500), message: "Would you take $15?", created_at: "2026-11-12T10:00:00Z" }],
    allowed_actions: [],
    customer: { id: CUSTOMER_ME.id, email: CUSTOMER_ME.email },
  };
}

function round(fake: Fake, actor: string, action: string, amount: number | null, message: string | null = null) {
  const rounds = fake.offer!.rounds as Json[];
  rounds.push({ sequence: rounds.length + 1, actor, action, amount: amount === null ? null : usd(amount), message, created_at: "2026-11-12T11:00:00Z" });
}

// The customer's / admin's view of the shared offer: allowed_actions follow
// the turn, exactly as negotiation/domain/offers.py `allowed_moves`.
function view(fake: Fake, who: "customer" | "admin"): Json {
  const offer = fake.offer!;
  const awaiting = offer.status === "awaiting_admin" || offer.status === "awaiting_customer";
  const myTurn = offer.turn === who;
  const allowed = !awaiting ? [] : who === "customer" ? [...(myTurn ? ["counter", "accept"] : []), "withdraw"] : myTurn ? ["counter", "accept", "reject"] : [];
  if (who === "admin") return { ...offer, allowed_actions: allowed };
  const { customer: _customer, ...rest } = offer;
  return { ...rest, allowed_actions: allowed };
}

async function install(page: Page, me: Json | null, initial: Json | null = null): Promise<Fake> {
  const fake: Fake = { offer: initial, writes: [], failNext: new Map() };
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  const record = (route: Route) => {
    const r = route.request();
    const raw = r.postData();
    fake.writes.push({ path: new URL(r.url()).pathname, body: raw ? JSON.parse(raw) : null, csrf: r.headers()["x-csrf-token"] ?? null, key: r.headers()["idempotency-key"] ?? null });
  };
  const failed = (route: Route, name: string) => {
    const failure = fake.failNext.get(name);
    if (!failure) return false;
    fake.failNext.delete(name);
    void route.fulfill(failure);
    return true;
  };

  if (me) {
    await page.context().addCookies([{ name: "csrf_token", value: "e2e-csrf-value", url: "http://localhost:3000" }]);
    await stubEmptyCart(page);
    await page.route(/\/api\/v1\/me$/, (r) => json(r, me));
  } else {
    await page.route(/\/api\/v1\/me$/, (r) => r.fulfill(problem(401, "AUTH_REQUIRED")));
    await page.route(/\/api\/v1\/auth\/refresh$/, (r) => r.fulfill(problem(401, "AUTH_REQUIRED")));
  }
  await page.route(/\/api\/v1\/settings\/public$/, (r) =>
    json(r, { accepting_orders: true, cash_payment_enabled: false, cash_max_order_total: null, pickup_address: null, pickup_hours: null, whatsapp_number: null })
  );
  await page.route(/\/api\/v1\/products\/dragon-stl$/, (r) => json(r, STL_DETAIL));
  await page.route(/\/api\/v1\/notifications(\?.*)?$/, (r) => json(r, { items: [], next_cursor: null, unread_count: 0 }));

  // --- customer ---
  await page.route(/\/api\/v1\/me\/offers(\?.*)?$/, (r) => json(r, { items: fake.offer ? [view(fake, "customer")] : [], next_cursor: null }));
  await page.route(/\/api\/v1\/me\/offers\/[^/?]+$/, (r) => (fake.offer ? json(r, view(fake, "customer")) : r.fulfill(problem(404, "NOT_FOUND"))));
  await page.route(/\/api\/v1\/offers$/, (route) => {
    record(route);
    if (failed(route, "create")) return;
    const body = route.request().postDataJSON() as Json;
    fake.offer = { ...baseOffer(), current_amount: usd(body.amount_cents as number), initial_amount: usd(body.amount_cents as number) };
    (fake.offer.rounds as Json[])[0] = { sequence: 1, actor: "customer", action: "submitted", amount: usd(body.amount_cents as number), message: body.message ?? null, created_at: "2026-11-12T10:00:00Z" };
    return json(route, view(fake, "customer"), 201);
  });
  await page.route(/\/api\/v1\/me\/offers\/[^/]+\/(counter|accept|withdraw)$/, (route) => {
    record(route);
    const action = new URL(route.request().url()).pathname.split("/").pop()!;
    if (failed(route, action)) return;
    const body = (route.request().postDataJSON() ?? {}) as Json;
    const offer = fake.offer!;
    if (action === "counter") {
      Object.assign(offer, { status: "awaiting_admin", turn: "admin", current_amount: usd(body.amount_cents as number) });
      round(fake, "customer", "countered", body.amount_cents as number, (body.message as string) ?? null);
    } else if (action === "accept") {
      Object.assign(offer, { status: "accepted", turn: null, agreed_amount: offer.current_amount, responds_by: null, checkout_expires_at: "2026-11-13T10:00:00Z" });
      round(fake, "customer", "accepted", (offer.current_amount as Json).amount_cents as number);
    } else {
      Object.assign(offer, { status: "withdrawn", turn: null });
      round(fake, "customer", "withdrawn", null, (body.reason as string) ?? null);
    }
    return json(route, view(fake, "customer"));
  });
  await page.route(/\/api\/v1\/me\/offers\/[^/]+\/checkout$/, (route) => {
    record(route);
    if (failed(route, "checkout")) return;
    return json(
      route,
      {
        order: {
          id: ORDER_ID, order_number: "B3D-OFFR0001", source: "offer", status: "pending_payment", payment_method: "online", fulfillment_method: null,
          subtotal: usd(1800), tax: usd(0), total: usd(1800), placed_at: "2026-11-12T12:00:00Z", estimated_dispatch_at: null, delivery_fee_note: null,
          delivery_address: null, payment_due: false, amount_due: null,
          lines: [{ id: uuid(702), product_id: PRODUCT_ID, product_type: "stl", name: "Dragon STL", unit_price: usd(1800), quantity: 1, line_total: usd(1800), fulfillment_status: "pending" }],
        },
        payment: { id: uuid(703), status: "pending", provider: "mock", redirect_url: "http://localhost:3000/__e2e-mock-pay" },
        dropped_lines: [],
      },
      201
    );
  });
  await page.route(/\/__e2e-mock-pay$/, (r) => r.fulfill({ status: 200, contentType: "text/html", body: "<html><body><h1>Mock payment page</h1></body></html>" }));

  // --- admin ---
  await page.route(/\/api\/v1\/admin\/offers(\?.*)?$/, (r) => json(r, { items: fake.offer ? [view(fake, "admin")] : [], next_cursor: null }));
  await page.route(/\/api\/v1\/admin\/offers\/[^/?]+$/, (r) => (fake.offer ? json(r, view(fake, "admin")) : r.fulfill(problem(404, "NOT_FOUND"))));
  await page.route(/\/api\/v1\/admin\/offers\/[^/]+\/(counter|accept|reject)$/, (route) => {
    record(route);
    const action = new URL(route.request().url()).pathname.split("/").pop()!;
    if (failed(route, `admin-${action}`)) return;
    const body = (route.request().postDataJSON() ?? {}) as Json;
    const offer = fake.offer!;
    if (offer.turn !== "admin") return route.fulfill(problem(409, "OFFER_NOT_YOUR_TURN"));
    if (action === "counter") {
      Object.assign(offer, { status: "awaiting_customer", turn: "customer", current_amount: usd(body.amount_cents as number) });
      round(fake, "admin", "countered", body.amount_cents as number, (body.message as string) ?? null);
    } else if (action === "accept") {
      Object.assign(offer, { status: "accepted", turn: null, agreed_amount: offer.current_amount, responds_by: null, checkout_expires_at: "2026-11-13T10:00:00Z" });
      round(fake, "admin", "accepted", (offer.current_amount as Json).amount_cents as number);
    } else {
      Object.assign(offer, { status: "rejected", turn: null, cooldown_until: "2026-11-19T10:00:00Z" });
      round(fake, "admin", "rejected", null, (body.reason as string) ?? null);
    }
    return json(route, view(fake, "admin"));
  });
  return fake;
}

async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

function countered(): Json {
  const offer = baseOffer();
  Object.assign(offer, { status: "awaiting_customer", turn: "customer", current_amount: usd(1800) });
  (offer.rounds as Json[]).push({ sequence: 2, actor: "admin", action: "countered", amount: usd(1800), message: "We can do $18.", created_at: "2026-11-12T10:30:00Z" });
  return offer;
}

test.describe("Offers (Phase 6C)", () => {
  test("anonymous: Make an offer is a sign-in link and no offer request is sent", async ({ page }) => {
    const offerRequests: string[] = [];
    page.on("request", (req) => {
      if (/\/api\/v1\/(me\/)?offers/.test(new URL(req.url()).pathname)) offerRequests.push(req.url());
    });
    await install(page, null);
    await page.goto("/shop/dragon-stl");
    await expect(page.getByRole("heading", { name: "Dragon STL" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Make an offer" })).toHaveAttribute("href", "/login?returnTo=%2Fshop%2Fdragon-stl");
    expect(offerRequests).toEqual([]);
  });

  test("no Make an offer without the server's can_offer capability", async ({ page }) => {
    await install(page, CUSTOMER_ME);
    await page.route(/\/api\/v1\/products\/dragon-stl$/, (r) =>
      r.fulfill({ contentType: "application/json", body: JSON.stringify({ ...STL_DETAIL, capabilities: { ...STL_DETAIL.capabilities, can_offer: false } }) })
    );
    await page.goto("/shop/dragon-stl");
    await expect(page.getByRole("heading", { name: "Dragon STL" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Make an offer" })).toHaveCount(0);
  });

  test("create: CSRF refusal is safe copy; then the offer is sent exactly, listed, and opened", async ({ page }) => {
    const fake = await install(page, CUSTOMER_ME);
    fake.failNext.set("create", problem(403, "CSRF_INVALID"));
    await page.goto("/shop/dragon-stl");
    await page.getByRole("button", { name: "Make an offer" }).click();
    await page.getByLabel("Your offer (USD)").fill("15");
    await page.getByLabel("Message (optional)").fill("Would you take $15?");
    await page.getByRole("button", { name: "Send offer" }).click();
    await expect(page.getByText("Unable to verify your session. Please refresh the page and try again.")).toBeVisible();
    await expect(page.getByText(/RAW/)).toHaveCount(0);

    await page.getByRole("button", { name: "Send offer" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Your offer was sent." })).toBeVisible();
    expect(fake.writes.at(-1)).toEqual({
      path: "/api/v1/offers",
      body: { product_id: PRODUCT_ID, amount_cents: 1500, currency: "USD", message: "Would you take $15?" },
      csrf: "e2e-csrf-value",
      key: null,
    });
    // The form gives way to the live offer.
    await expect(page.getByRole("button", { name: "Make an offer" })).toHaveCount(0);

    await page.goto("/account/offers");
    await expect(page.getByRole("heading", { level: 1, name: "Offers" })).toBeVisible();
    await page.getByRole("link", { name: "Offer on Dragon STL" }).click();
    await expect(page).toHaveURL(new RegExp(`/account/offers/${OFFER_ID}$`));
    await expect(page.getByText("Waiting for our reply")).toBeVisible();
    await expect(page.getByText("You offered $15.00")).toBeVisible();
    await expect(page.getByRole("region", { name: "Your reply" }).getByRole("button")).toHaveText(["Withdraw offer"]);
  });

  test("counter survives a session refresh; an invalid transition refreshes the real state", async ({ page }) => {
    const fake = await install(page, CUSTOMER_ME, countered());
    fake.failNext.set("counter", problem(401, "AUTH_REQUIRED"));
    await page.goto(`/account/offers/${OFFER_ID}`);
    await expect(page.getByText("Your reply needed")).toBeVisible();
    await expect(page.getByText("We can do $18.")).toBeVisible();

    await page.getByRole("button", { name: "Counter-offer" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Your counter-offer (USD)").fill("16.50");
    await dialog.getByRole("button", { name: "Send counter-offer" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Your counter-offer was sent." })).toBeVisible();
    const counters = fake.writes.filter((w) => w.path.endsWith("/counter"));
    expect(counters).toHaveLength(2); // 401, then the one retry after the session check
    expect(counters[1]).toMatchObject({ body: { amount_cents: 1650, currency: "USD" }, csrf: "e2e-csrf-value" });
    await expect(page.getByText("Waiting for our reply")).toBeVisible();

    // Someone else moved it on: the page says so and shows the real state.
    fake.offer = countered();
    await page.reload();
    fake.failNext.set("accept", problem(409, "INVALID_STATE_TRANSITION", { offer_status: "expired" }));
    await page.getByRole("button", { name: "Accept this amount" }).click();
    Object.assign(fake.offer, { status: "expired", turn: null });
    await page.getByRole("dialog").getByRole("button", { name: "Accept" }).click();
    await expect(page.getByText("This offer has already moved on")).toBeVisible();
    await expect(page.getByText("Expired", { exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: "Your reply" })).toHaveCount(0);
  });

  test("accept then check out at the agreed price with one idempotency key, following the server's redirect", async ({ page }) => {
    const fake = await install(page, CUSTOMER_ME, countered());
    await page.goto(`/account/offers/${OFFER_ID}`);
    await page.getByRole("button", { name: "Accept this amount" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Accept" }).click();
    await expect(page.getByText("Accepted: ready to check out")).toBeVisible();
    expect(fake.writes.at(-1)).toMatchObject({ path: `/api/v1/me/offers/${OFFER_ID}/accept`, body: { expected_amount_cents: 1800 } });

    const panel = page.getByRole("region", { name: "Check out at the agreed price" });
    await expect(panel).toContainText("$18.00");
    fake.failNext.set("checkout", problem(500, "INTERNAL_ERROR"));
    await panel.getByLabel(/terms of sale/).check();
    await panel.getByLabel(/final sale/).check();
    await panel.getByRole("button", { name: "Check out and pay" }).click();
    await expect(panel.getByRole("heading", { name: "Checking your order" })).toBeVisible();
    await panel.getByRole("button", { name: "Try again" }).click();
    await expect(page).toHaveURL(/__e2e-mock-pay$/);
    const checkouts = fake.writes.filter((w) => w.path.endsWith("/checkout"));
    expect(checkouts).toHaveLength(2);
    expect(checkouts[0]!.key).toMatch(/^[A-Za-z0-9._:-]{8,255}$/);
    expect(checkouts[1]!.key).toBe(checkouts[0]!.key);
    expect(checkouts[1]!.body).toEqual({ accept_terms: true, accept_digital_final_sale: true });
  });

  test("admin queue and detail: counter exactly, then the customer's turn has no admin actions", async ({ page }) => {
    const fake = await install(page, ADMIN_ME, baseOffer());
    await page.goto("/admin/offers");
    await expect(page.getByRole("heading", { level: 1, name: "Offers" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "Your reply needed" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "rana@example.com" })).toBeVisible();
    await page.getByRole("link", { name: "Dragon STL" }).click();
    await expect(page).toHaveURL(new RegExp(`/admin/offers/${OFFER_ID}$`));
    await expect(page.getByText("Customer offered $15.00")).toBeVisible();
    await expect(page.getByRole("region", { name: "Your reply" }).getByRole("button")).toHaveText(["Accept offer", "Counter-offer", "Reject offer"]);

    await page.getByRole("button", { name: "Counter-offer" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Your counter-offer (USD)").fill("18");
    await dialog.getByLabel("Message (optional)").fill("We can do $18.");
    await dialog.getByRole("button", { name: "Send counter-offer" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Counter-offer sent." })).toBeVisible();
    expect(fake.writes.at(-1)).toEqual({
      path: `/api/v1/admin/offers/${OFFER_ID}/counter`,
      body: { amount_cents: 1800, currency: "USD", message: "We can do $18." },
      csrf: "e2e-csrf-value",
      key: null,
    });
    await expect(page.getByText("Waiting for the customer", { exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: "Your reply" })).toHaveCount(0);
  });

  test("admin reject goes through a destructive confirmation; a CSRF refusal keeps the dialog open", async ({ page }) => {
    const fake = await install(page, ADMIN_ME, baseOffer());
    fake.failNext.set("admin-reject", problem(403, "CSRF_INVALID"));
    await page.goto(`/admin/offers/${OFFER_ID}`);
    await page.getByRole("region", { name: "Your reply" }).getByRole("button", { name: "Reject offer" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Reason for the customer (optional)").fill("Too low");
    await dialog.getByRole("button", { name: "Reject offer" }).click();
    await expect(dialog.getByText("Unable to verify your session")).toBeVisible();
    await dialog.getByRole("button", { name: "Reject offer" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Offer rejected." })).toBeVisible();
    expect(fake.writes.at(-1)).toMatchObject({ path: `/api/v1/admin/offers/${OFFER_ID}/reject`, body: { reason: "Too low" } });
    await expect(page.getByText("Rejected", { exact: true })).toBeVisible();
  });

  test("a signed-in customer on /admin/offers sees the real 404", async ({ page }) => {
    await install(page, CUSTOMER_ME, baseOffer());
    await page.goto("/admin/offers");
    await expect(page.getByText(/404/)).toBeVisible();
    await expect(page.getByText("rana@example.com")).toHaveCount(0);
  });

  test("keyboard: the move dialog opens with Enter, closes with Escape and returns focus; mobile has no horizontal scroll", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 740 });
    await install(page, CUSTOMER_ME, countered());
    await page.goto(`/account/offers/${OFFER_ID}`);
    const trigger = page.getByRole("button", { name: "Counter-offer" });
    await trigger.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog")).toBeVisible();
    await noHorizontalScroll(page);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await noHorizontalScroll(page);

    await page.goto("/account/offers");
    await expect(page.getByRole("link", { name: "Offer on Dragon STL" })).toBeVisible();
    await noHorizontalScroll(page);
  });
});
