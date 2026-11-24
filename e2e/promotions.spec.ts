import { test, expect, type Page, type Route } from "@playwright/test";
import { stubEmptyWishlist } from "./support/stubCart";
import { E2E_ORIGIN } from "./support/origin";

// Seasonal promotions — admin creates and activates a promotion → the
// homepage shows the campaign → the covered product shows its discount →
// the cart and checkout carry the backend's price.
//
// A deterministic, in-memory stand-in for the real contract (backend
// docs/promotions.md, openapi.json): the FAKE SERVER, like the real one,
// owns pricing — it lowers `price` while its promotion is active and the
// cart reads the same price. The frontend never computes one; the checks
// below confirm it only ever shows and sends what the server said.

const CSRF = "e2e-csrf-value";
const USD = (amount_cents: number) => ({ amount_cents, currency: "USD" });

const ADMIN = {
  id: "admin-1",
  email: "admin@example.com",
  role: "admin",
  email_verified: true,
  email_verified_at: "2025-01-01T00:00:00Z",
  created_at: "2024-01-01T00:00:00Z",
};
const CUSTOMER = { ...ADMIN, id: "u-1", email: "ada@example.com", role: "customer" };

const PRODUCT = { id: "p-dragon-stl", slug: "dragon-stl", name: "Dragon STL", listCents: 2500 };

type Json = Record<string, unknown>;

interface Fake {
  me: Json;
  promotion: Json | null;
  cart: { snapshotCents: number }[];
  writes: { path: string; body: Json | null; csrf: string | undefined }[];
}

// The server's own price rule for this one product (20% of 2500 = 500 off).
function serverPrice(fake: Fake): number {
  const p = fake.promotion;
  if (!p || p.active !== true) return PRODUCT.listCents;
  const value = p.discount_value as number;
  const off = p.discount_type === "percentage" ? Math.round((PRODUCT.listCents * value) / 100) : value;
  return Math.max(PRODUCT.listCents - off, 0);
}

function productBody(fake: Fake): Json {
  const price = serverPrice(fake);
  const p = fake.promotion;
  return {
    id: PRODUCT.id,
    type: "stl",
    name: PRODUCT.name,
    slug: PRODUCT.slug,
    cover_image: null,
    price: USD(price),
    list_price: USD(PRODUCT.listCents),
    promotion:
      p && price < PRODUCT.listCents
        ? {
            id: p.id,
            name: p.name,
            badge_text: p.badge_text,
            discount_type: p.discount_type,
            discount_value: p.discount_value,
            ends_at: p.ends_at,
          }
        : null,
    category: { id: "c1", name: "Toys and Figures", slug: "toys-figures" },
    material: null,
    colour: null,
    is_available: true,
    purchase_mode: null,
    accepted_payment_methods: null,
    average_rating: 0,
    review_count: 0,
    is_featured: true,
    description: null,
    images: [],
    seo_title: null,
    seo_description: null,
    og_image_url: null,
    dimensions: null,
    production_lead_time_days: null,
    batch_size: null,
    max_quantity_per_line: null,
    capabilities: { can_add_to_cart: true, can_offer: false, whatsapp_available: false },
  };
}

function cartBody(fake: Fake): Json {
  const current = serverPrice(fake);
  const items = fake.cart.map((line) => ({
    product_id: PRODUCT.id,
    product_type: "stl",
    name: PRODUCT.name,
    slug: PRODUCT.slug,
    cover_image: null,
    quantity: 1,
    snapshot_price: USD(line.snapshotCents),
    current_price: USD(current),
    price_changed: line.snapshotCents !== current,
    max_quantity: null,
    over_cap: false,
    purchasable: true,
    unpurchasable_reason: null,
  }));
  return {
    id: fake.cart.length ? "cart-1" : null,
    items,
    contains_physical: false,
    contains_digital: items.length > 0,
    payment_methods: ["online"],
    updated_at: fake.cart.length ? "2026-11-24T10:00:00Z" : null,
  };
}

async function install(page: Page): Promise<Fake> {
  const fake: Fake = { me: ADMIN, promotion: null, cart: [], writes: [] };
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  const record = (route: Route) => {
    const r = route.request();
    fake.writes.push({ path: new URL(r.url()).pathname, body: r.postData() ? (r.postDataJSON() as Json) : null, csrf: r.headers()["x-csrf-token"] });
  };

  await page.context().addCookies([{ name: "csrf_token", value: CSRF, url: E2E_ORIGIN }]);
  await stubEmptyWishlist(page);
  await page.route(/\/api\/v1\/me$/, (r) => json(r, fake.me));
  await page.route(/\/api\/v1\/notifications(\?.*)?$/, (r) => json(r, { items: [], next_cursor: null, unread_count: 0 }));
  await page.route(/\/api\/v1\/settings\/public$/, (r) =>
    json(r, { accepting_orders: true, cash_payment_enabled: false, cash_max_order_total: USD(10000), pickup_address: null, pickup_hours: null, whatsapp_number: null })
  );
  await page.route(/\/api\/v1\/(categories|materials|colours)$/, (r) => json(r, { items: [] }));
  await page.route(/\/api\/v1\/promotions$/, (r) =>
    json(r, { items: fake.promotion?.active ? [{ ...fake.promotion }] : [] })
  );
  await page.route(/\/api\/v1\/admin\/promotions$/, (route) => {
    if (route.request().method() === "POST") {
      record(route);
      const body = route.request().postDataJSON() as Json;
      fake.promotion = { ...body, id: "promo-eid", product_ids: [], status: body.active ? "active" : "inactive", created_at: "2026-11-24T10:00:00Z", updated_at: "2026-11-24T10:00:00Z" };
      return json(route, fake.promotion, 201);
    }
    return json(route, { items: fake.promotion ? [fake.promotion] : [] });
  });
  await page.route(/\/api\/v1\/products(\?.*)?$/, (route) => {
    const url = new URL(route.request().url());
    const promotionId = url.searchParams.get("promotion_id");
    const covered = !promotionId || (fake.promotion?.active === true && promotionId === fake.promotion.id);
    return json(route, { items: covered ? [productBody(fake)] : [], next_cursor: null });
  });
  await page.route(/\/api\/v1\/products\/dragon-stl$/, (r) => json(r, productBody(fake)));
  await page.route(/\/api\/v1\/cart$/, (r) => json(r, cartBody(fake)));
  await page.route(/\/api\/v1\/cart\/items$/, (route) => {
    record(route);
    // The server snapshots ITS price at add-to-cart; the client sends none.
    fake.cart = [{ snapshotCents: serverPrice(fake) }];
    return json(route, cartBody(fake));
  });
  await page.route(/\/api\/v1\/checkout$/, (route) => {
    record(route);
    const total = serverPrice(fake);
    fake.cart = [];
    return json(
      route,
      {
        order: {
          id: "00000000-0000-4000-8000-000000000901",
          order_number: "B3D-PROMO001",
          source: "cart",
          status: "pending_payment",
          payment_method: "online",
          fulfillment_method: null,
          subtotal: USD(total),
          tax: USD(0),
          total: USD(total),
          placed_at: "2026-11-24T10:00:00Z",
          estimated_dispatch_at: null,
          delivery_fee_note: null,
          lines: [
            { id: "line-1", product_id: PRODUCT.id, product_type: "stl", name: PRODUCT.name, unit_price: USD(total), quantity: 1, line_total: USD(total), fulfillment_status: "pending" },
          ],
        },
        payment: { id: "pay-1", status: "pending", provider: "mock", redirect_url: `${E2E_ORIGIN}/__e2e-mock-pay`, next_step: "redirect", hold_expires_at: "2026-11-24T10:30:00Z" },
        dropped_lines: [],
      },
      201
    );
  });
  await page.route(/\/__e2e-mock-pay$/, (r) => r.fulfill({ status: 200, contentType: "text/html", body: "<html><body><h1>Mock payment page</h1></body></html>" }));
  return fake;
}

test.describe("Seasonal promotions", () => {
  test("no active promotion: the homepage shows no campaign banner and no placeholder", async ({ page }) => {
    const fake = await install(page);
    fake.me = CUSTOMER;
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("link", { name: /shop promotion/i })).toHaveCount(0);
    await expect(page.getByText(/Storewide Launch|Redeem discount/i)).toHaveCount(0);
  });

  test("admin creates and activates a promotion → homepage → product → cart → checkout all carry the server's price", async ({ page }) => {
    const fake = await install(page);

    // --- admin creates and activates the promotion
    await page.goto("/admin/promotions/new");
    await page.getByLabel("Promotion name").fill("Eid Sale");
    await page.getByLabel("Badge text (optional)").fill("Eid al-Fitr");
    await page.getByLabel("Discount value (%)").fill("20");
    await expect(page.getByRole("switch", { name: "Active" })).toHaveAttribute("aria-checked", "true");
    await page.getByRole("button", { name: "Save promotion" }).click();
    await expect(page).toHaveURL(/\/admin\/promotions$/);
    await expect(page.getByRole("link", { name: "Eid Sale" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "Active" })).toBeVisible();
    const created = fake.writes.find((w) => w.path === "/api/v1/admin/promotions");
    expect(created?.csrf).toBe(CSRF);
    expect(created?.body).toMatchObject({ name: "Eid Sale", badge_text: "Eid al-Fitr", discount_type: "percentage", discount_value: 20, scope: "all", product_ids: [], active: true });

    // --- the homepage shows the server's campaign
    fake.me = CUSTOMER;
    await page.goto("/");
    const banner = page.getByRole("region", { name: /20% OFF\s*Eid Sale/ });
    await expect(banner).toBeVisible();
    await expect(banner.getByText("Eid al-Fitr")).toBeVisible();
    await banner.getByRole("link", { name: /shop promotion/i }).click();
    await expect(page).toHaveURL(/\/shop\?promotion=promo-eid$/);
    await expect(page.getByText(/Showing products in the/)).toContainText("Eid Sale");

    // --- the covered product shows the server's discounted price
    const card = page.getByRole("link", { name: /Dragon STL/ }).first();
    await expect(card).toContainText("-20%");
    await expect(card).toContainText(/Current promotional price:\s*\$20\.00/);
    await expect(card).toContainText(/Original price:\s*\$25\.00/);
    await card.click();
    await expect(page.getByRole("heading", { level: 1, name: "Dragon STL" })).toBeVisible();
    await expect(page.getByText("$20.00").first()).toBeVisible();
    await expect(page.getByText("20% OFF")).toBeVisible();

    // --- the cart carries the backend's price; the client sent no price
    await page.getByRole("button", { name: /add to cart/i }).click();
    const added = fake.writes.find((w) => w.path === "/api/v1/cart/items");
    expect(JSON.stringify(added?.body)).not.toMatch(/price|amount|discount/);
    await page.goto("/cart");
    await expect(page.getByText("$20.00").first()).toBeVisible();
    await expect(page.getByText("$25.00")).toHaveCount(0);

    // --- checkout charges the backend's price
    await page.goto("/checkout");
    await expect(page.getByText("$20.00").first()).toBeVisible();
    await page.getByRole("radio", { name: /Pay online/ }).check();
    await page.getByRole("checkbox", { name: /terms of sale/ }).check();
    await page.getByRole("checkbox", { name: /digital/i }).check();
    await page.getByRole("button", { name: "Place order" }).click();
    await expect(page).toHaveURL(/__e2e-mock-pay$/);
    const placed = fake.writes.find((w) => w.path === "/api/v1/checkout");
    expect(JSON.stringify(placed?.body)).not.toMatch(/price|amount|discount|promotion/);
  });
});
