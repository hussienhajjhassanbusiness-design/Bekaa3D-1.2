import { test, expect, type Locator, type Page, type Route } from "@playwright/test";
import { E2E_ORIGIN } from "./support/origin";

// Redesign Batch 6 — /cart and /checkout at the six QA widths, against
// mocked real-shaped data (route interception only; no backend). Asserts
// user-facing intent, not classes: one h1, no horizontal overflow, line
// actions stay inside their card at a 44px target size, the summary sits
// beside the content from 1024px (and stays clear of the 64px sticky
// header while scrolling) and after it below that, and the checkout
// states that change the layout (pickup, STL only, price change, refused
// lines) still fit at 320px.

const WIDTHS = [320, 375, 768, 1024, 1280, 1440];
const CSRF = "e2e-csrf-value";

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
  pickup_address: "Bekaa3D workshop, Industrial Zone, Zahle — second building behind the municipal garden",
  pickup_hours: "Mon-Fri 10:00-18:00",
  whatsapp_number: "+96170000000",
};

const ADDRESSES = [
  {
    id: "a-home",
    label: "Grandparents' house in the mountains above Jounieh",
    recipient_name: "Marie-Thérèse Abou Khalil El Haddad",
    phone: "+961 71 123 456",
    governorate: "keserwan_jbeil",
    city: "Jounieh",
    area: "Sahel Alma, near the Notre-Dame du Liban funicular",
    street: "Rue Mar Elias, Building Khoury-Sfeir, third floor",
    landmark_notes: "Blue gate next to the bakery",
    is_default: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "a-work",
    label: "Work",
    recipient_name: "Ada",
    phone: "03 123 456",
    governorate: "beqaa",
    city: "Zahle",
    area: null,
    street: "Main St",
    landmark_notes: "Reception",
    is_default: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

const usd = (amount_cents: number) => ({ amount_cents, currency: "USD" });

function item(overrides: Record<string, unknown>) {
  return {
    product_type: "physical",
    cover_image: null,
    quantity: 1,
    snapshot_price: usd(1800),
    current_price: usd(1800),
    price_changed: false,
    max_quantity: 5,
    over_cap: false,
    purchasable: true,
    unpurchasable_reason: null,
    ...overrides,
  };
}

const LONG_NAME =
  "Articulated Dragon with Fully Posable Wings, Interlocking Tail Segments and Display Stand — Extra Large Edition";

// Every cart state the redesign must keep visible: a long title with a
// price change, an STL line, an unavailable line and an over-cap line.
const CART_ALL_STATES = {
  id: "cart-1",
  items: [
    item({
      product_id: "p-long",
      name: LONG_NAME,
      slug: "dragon-xl",
      quantity: 2,
      snapshot_price: usd(1500),
      price_changed: true,
    }),
    item({
      product_id: "p-stl",
      product_type: "stl",
      name: "Dragon STL",
      slug: "dragon-stl",
      max_quantity: null,
      snapshot_price: usd(900),
      current_price: usd(900),
    }),
    item({
      product_id: "p-vase",
      name: "Spiral Vase",
      slug: "spiral-vase",
      purchasable: false,
      unpurchasable_reason: "unavailable",
    }),
    item({
      product_id: "p-gear",
      name: "Planetary Gear Set",
      slug: "gear-set",
      quantity: 6,
      max_quantity: 3,
      over_cap: true,
    }),
  ],
  contains_physical: true,
  contains_digital: true,
  updated_at: null,
};

const CART_PHYSICAL = {
  id: "cart-1",
  items: [
    item({ product_id: "p-long", name: LONG_NAME, slug: "dragon-xl", quantity: 2 }),
    item({
      product_id: "p-vase",
      name: "Spiral Vase",
      slug: "spiral-vase",
      snapshot_price: usd(2200),
      current_price: usd(2200),
    }),
  ],
  contains_physical: true,
  contains_digital: false,
  updated_at: null,
};

const CART_STL_ONLY = {
  id: "cart-1",
  items: [
    item({
      product_id: "p-stl",
      product_type: "stl",
      name: "Dragon STL",
      slug: "dragon-stl",
      max_quantity: null,
      snapshot_price: usd(900),
      current_price: usd(900),
    }),
  ],
  contains_physical: false,
  contains_digital: true,
  updated_at: null,
};

function problem(route: Route, status: number, code: string, extensions: Record<string, unknown> = {}) {
  return route.fulfill({
    status,
    contentType: "application/problem+json",
    body: JSON.stringify({
      type: "about:blank",
      title: "RAW TITLE",
      status,
      detail: "RAW DETAIL",
      code,
      errors: [],
      ...extensions,
    }),
  });
}

async function install(page: Page, cart: unknown, checkout?: (route: Route) => Promise<void>) {
  await page.context().addCookies([{ name: "csrf_token", value: CSRF, url: E2E_ORIGIN }]);
  await page.route(/\/api\/v1\/me$/, (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(ME) })
  );
  await page.route(/\/api\/v1\/settings\/public$/, (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(SETTINGS) })
  );
  await page.route(/\/api\/v1\/me\/addresses$/, (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: ADDRESSES }) })
  );
  await page.route(/\/api\/v1\/cart$/, (route) =>
    route.request().method() === "GET"
      ? route.fulfill({ contentType: "application/json", body: JSON.stringify(cart) })
      : problem(route, 405, "METHOD_NOT_ALLOWED")
  );
  await page.route(/\/api\/v1\/checkout$/, (route) =>
    checkout ? checkout(route) : problem(route, 503, "SERVICE_UNAVAILABLE")
  );
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

async function headerBottom(page: Page): Promise<number> {
  const box = (await page.getByRole("banner").boundingBox())!;
  return box.y + box.height;
}

// Scroll 150px into the two-column area (inside the sticky range: the main
// column is much taller than the summary) and check the summary is pinned
// just below the sticky header, never behind it.
async function expectPinnedBelowHeader(page: Page, area: Locator, summary: Locator) {
  const top = (await area.boundingBox())!.y;
  await page.evaluate((offset) => window.scrollBy(0, offset), top + 150);
  const bottom = await headerBottom(page);
  await expect.poll(async () => (await summary.boundingBox())!.y).toBeGreaterThanOrEqual(bottom);
  expect((await summary.boundingBox())!.y).toBeLessThanOrEqual(bottom + 48);
}

test.describe("Cart and Checkout responsive (redesign Batch 6)", () => {
  for (const width of WIDTHS) {
    test(`/cart at ${width}px: every line state visible, actions inside cards, summary placement`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await install(page, CART_ALL_STATES);
      await page.goto("/cart");

      await expect(page.getByRole("heading", { level: 1, name: "Your cart" })).toBeVisible();
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
      await expect(page.getByRole("article")).toHaveCount(4);
      await expectNoHorizontalOverflow(page);

      // Each state is stated in text.
      const long = page.getByRole("article", { name: LONG_NAME });
      await expect(long.getByText("Price when added", { exact: true })).toBeVisible();
      await expect(long.getByText("Current price", { exact: true })).toBeVisible();
      await expect(
        page.getByRole("article", { name: "Dragon STL" }).getByText("STL files are sold one copy per order.")
      ).toBeVisible();
      await expect(
        page.getByRole("article", { name: "Spiral Vase" }).getByText(/currently unavailable/i)
      ).toBeVisible();
      await expect(
        page.getByRole("article", { name: "Planetary Gear Set" }).getByText(/at most 3 of this product/i)
      ).toBeVisible();
      await expect(page.getByRole("button", { name: "Proceed to checkout" })).toBeDisabled();

      // Line actions stay inside their card and are practical targets.
      for (const article of await page.getByRole("article").all()) {
        const card = (await article.boundingBox())!;
        for (const button of await article.getByRole("button").all()) {
          const box = (await button.boundingBox())!;
          expect(box.height).toBeGreaterThanOrEqual(44);
          expect(box.x).toBeGreaterThanOrEqual(card.x - 1);
          expect(box.x + box.width).toBeLessThanOrEqual(card.x + card.width + 1);
        }
      }

      const list = (await page.getByRole("list", { name: "Cart items" }).boundingBox())!;
      const summary = page.getByRole("region", { name: "Cart summary" });
      const summaryBox = (await summary.boundingBox())!;
      if (width >= 1024) {
        expect(summaryBox.x).toBeGreaterThanOrEqual(list.x + list.width);
        await expectPinnedBelowHeader(page, page.getByRole("list", { name: "Cart items" }), summary);
      } else {
        expect(summaryBox.y).toBeGreaterThanOrEqual(list.y + list.height);
      }
    });

    test(`/checkout at ${width}px: delivery with long addresses, summary placement, Place order reachable`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 });
      await install(page, CART_PHYSICAL);
      await page.goto("/checkout");

      await expect(page.getByRole("heading", { level: 1, name: "Checkout" })).toBeVisible();
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
      await page.getByRole("radio", { name: /^Delivery/ }).check();
      await expect(page.getByRole("radio", { name: /Grandparents/ })).toBeChecked();
      await page.getByRole("radio", { name: /Pay in cash/ }).check();
      await page.getByRole("checkbox", { name: /pay the full amount in cash/ }).check();
      await expectNoHorizontalOverflow(page);

      const place = page.getByRole("button", { name: "Place order" });
      expect((await place.boundingBox())!.height).toBeGreaterThanOrEqual(44);

      const decisions = (await page.getByRole("group", { name: "Confirm" }).boundingBox())!;
      const summary = page.getByRole("complementary", { name: "Order summary" });
      const summaryBox = (await summary.boundingBox())!;
      if (width >= 1024) {
        expect(summaryBox.x).toBeGreaterThanOrEqual(decisions.x + decisions.width);
        await expectPinnedBelowHeader(page, page.getByRole("group", { name: "Delivery or pickup" }), summary);
      } else {
        expect(summaryBox.y).toBeGreaterThanOrEqual(decisions.y + decisions.height);
      }
    });
  }

  test("320px: pickup, STL-only, price change and refused lines all fit without horizontal scroll", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 320, height: 800 });
    let mode: "price" | "refused" = "price";
    await install(page, CART_PHYSICAL, (route) =>
      mode === "price"
        ? problem(route, 409, "CART_PRICE_CHANGED", {
            price_changes: [{ product_id: "p-long", old_amount_cents: 1800, new_amount_cents: 2100, currency: "USD" }],
          })
        : problem(route, 422, "PRODUCT_NOT_PURCHASABLE", { lines: [{ product_id: "p-vase", reason: "unavailable" }] })
    );
    await page.goto("/checkout");

    await page.getByRole("radio", { name: /^Pickup/ }).check();
    await expect(page.getByLabel("Contact phone")).toBeVisible();
    await page.getByLabel("Contact phone").fill("70 123 456");
    await expectNoHorizontalOverflow(page);

    await page.getByRole("radio", { name: /Pay online/ }).check();
    await page.getByRole("checkbox", { name: /terms of sale/ }).check();
    await page.getByRole("button", { name: "Place order" }).click();
    const banner = page.getByRole("alert").filter({ hasText: "Some prices have changed" });
    await expect(banner).toContainText("Was");
    await expect(banner).toContainText("Now");
    await expect(page.getByRole("button", { name: "Place order" })).toBeDisabled();
    await expectNoHorizontalOverflow(page);

    mode = "refused";
    await page.getByRole("button", { name: "Accept new prices" }).click();
    await page.getByRole("button", { name: "Place order" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "can't be ordered right now" })).toContainText(
      "Spiral Vase"
    );
    await expectNoHorizontalOverflow(page);

    await page.unrouteAll({ behavior: "ignoreErrors" });
    await install(page, CART_STL_ONLY);
    await page.goto("/checkout");
    await expect(page.getByRole("heading", { level: 2, name: "Delivery" })).toBeVisible();
    await expect(page.getByRole("radio", { name: /Pay in cash/ })).toBeDisabled();
    await expect(page.getByText("Not available")).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });
});
