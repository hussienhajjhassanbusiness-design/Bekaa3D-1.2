import { test, expect, type Page, type Route } from "@playwright/test";

// Phase 5C — /cart and product-page Add to cart (FVS-025) against a
// deterministic, in-memory stand-in for the real contract (openapi.json
// /api/v1/cart*, backend 2dfb27b docs/cart.md). Route interception only:
// no backend on :8000 and no media server on :8001 are needed (products
// have no images). The fake keeps state for the whole test (so a reload
// "persists") and applies the backend's documented rules: lines keyed by
// product_id, POST merges, physical quantity capped by
// max_quantity_per_line (422 QUANTITY_EXCEEDS_LIMIT, nothing clamped), STL
// quantity exactly 1 (re-adding is a no-op), refused products are 422
// PRODUCT_NOT_PURCHASABLE with `reason`, PATCH/DELETE of an absent line is
// 404, and every write without the matching X-CSRF-Token is 403.
//
// Route patterns are exact (`/api/v1/cart`, `/api/v1/cart/items`,
// `/api/v1/cart/items/{id}`, `/api/v1/products/{slug}`), so the catalogue
// list and other product slugs are never intercepted by accident.

const CSRF = "e2e-csrf-value";

const ME = {
  id: "u-1",
  email: "ada@example.com",
  role: "customer",
  email_verified: true,
  email_verified_at: "2025-01-01T00:00:00Z",
  created_at: "2024-01-01T00:00:00Z",
};

interface FakeProduct {
  id: string;
  type: "physical" | "stl";
  name: string;
  slug: string;
  priceCents: number;
  isAvailable: boolean;
  purchaseMode: "online_only" | "whatsapp_only" | "both" | null;
  maxQuantityPerLine: number | null;
}

const PRODUCTS: FakeProduct[] = [
  { id: "p-dragon", type: "physical", name: "Articulated Dragon", slug: "dragon", priceCents: 1800, isAvailable: true, purchaseMode: "both", maxQuantityPerLine: 3 },
  { id: "p-dragon-stl", type: "stl", name: "Dragon STL", slug: "dragon-stl", priceCents: 900, isAvailable: true, purchaseMode: null, maxQuantityPerLine: null },
  { id: "p-lamp", type: "physical", name: "Moon Lamp", slug: "moon-lamp", priceCents: 4000, isAvailable: true, purchaseMode: "whatsapp_only", maxQuantityPerLine: 2 },
  { id: "p-vase", type: "physical", name: "Spiral Vase", slug: "spiral-vase", priceCents: 2200, isAvailable: false, purchaseMode: "both", maxQuantityPerLine: 4 },
];

function refusal(product: FakeProduct): "unavailable" | "whatsapp_only" | null {
  if (!product.isAvailable) return "unavailable";
  if (product.purchaseMode === "whatsapp_only") return "whatsapp_only";
  return null;
}

function productDetail(product: FakeProduct) {
  const canAdd = refusal(product) === null;
  return {
    id: product.id,
    type: product.type,
    name: product.name,
    slug: product.slug,
    cover_image: null,
    price: { amount_cents: product.priceCents, currency: "USD" },
    category: { id: "c1", name: "Toys and Figures", slug: "toys-figures" },
    material: product.type === "physical" ? { id: "m1", name: "PLA" } : null,
    colour: null,
    is_available: product.isAvailable,
    purchase_mode: product.purchaseMode,
    average_rating: 0,
    review_count: 0,
    is_featured: false,
    description: null,
    images: [],
    seo_title: null,
    seo_description: null,
    og_image_url: null,
    dimensions: null,
    production_lead_time_days: null,
    batch_size: null,
    max_quantity_per_line: product.maxQuantityPerLine,
    capabilities: {
      can_add_to_cart: canAdd,
      can_offer: false,
      whatsapp_available: product.purchaseMode === "whatsapp_only" || product.purchaseMode === "both",
    },
  };
}

interface StoredLine {
  productId: string;
  quantity: number;
  snapshotCents: number;
}

interface FakeBackend {
  lines: StoredLine[];
  writes: { method: string; path: string; csrf: string | undefined; body: unknown }[];
}

function problem(route: Route, status: number, code: string, extensions: Record<string, unknown> = {}) {
  return route.fulfill({
    status,
    contentType: "application/problem+json",
    body: JSON.stringify({ type: "about:blank", title: "RAW TITLE", status, detail: "RAW DETAIL", code, errors: [], ...extensions }),
  });
}

function cartRead(backend: FakeBackend) {
  const items = backend.lines.map((line) => {
    const product = PRODUCTS.find((p) => p.id === line.productId)!;
    const reason = refusal(product);
    const cap = product.type === "physical" ? product.maxQuantityPerLine : null;
    return {
      product_id: product.id,
      product_type: product.type,
      name: product.name,
      slug: product.slug,
      cover_image: null,
      quantity: line.quantity,
      snapshot_price: { amount_cents: line.snapshotCents, currency: "USD" },
      current_price: { amount_cents: product.priceCents, currency: "USD" },
      price_changed: line.snapshotCents !== product.priceCents,
      max_quantity: cap,
      over_cap: cap !== null && line.quantity > cap,
      purchasable: reason === null,
      unpurchasable_reason: reason,
    };
  });
  return {
    id: backend.lines.length || backend.writes.length ? "cart-1" : null,
    items,
    contains_physical: items.some((item) => item.product_type === "physical"),
    contains_digital: items.some((item) => item.product_type === "stl"),
    updated_at: backend.writes.length ? "2026-11-11T10:00:00Z" : null,
  };
}

async function installFakeBackend(page: Page, initial: StoredLine[] = []): Promise<FakeBackend> {
  const backend: FakeBackend = { lines: initial.map((line) => ({ ...line })), writes: [] };

  await page.context().addCookies([{ name: "csrf_token", value: CSRF, url: "http://localhost:3000" }]);
  await page.route("**/api/v1/me", (route) => route.fulfill({ status: 200, body: JSON.stringify(ME) }));
  await page.route("**/api/v1/settings/public", (route) =>
    route.fulfill({
      body: JSON.stringify({
        accepting_orders: true,
        cash_payment_enabled: true,
        cash_max_order_total: { amount_cents: 10000, currency: "USD" },
        pickup_address: null,
        pickup_hours: null,
        whatsapp_number: "+96170000000",
      }),
    })
  );
  await page.route(/\/api\/v1\/products\/[^/?]+$/, (route) => {
    const slug = new URL(route.request().url()).pathname.split("/").pop();
    const product = PRODUCTS.find((p) => p.slug === slug);
    return product ? route.fulfill({ body: JSON.stringify(productDetail(product)) }) : problem(route, 404, "NOT_FOUND");
  });

  await page.route(/\/api\/v1\/cart(\/items(\/[^/]+)?)?$/, async (route) => {
    const request = route.request();
    const method = request.method();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/cart") {
      return method === "GET"
        ? route.fulfill({ status: 200, body: JSON.stringify(cartRead(backend)) })
        : problem(route, 405, "METHOD_NOT_ALLOWED");
    }

    const body = request.postData() ? request.postDataJSON() : undefined;
    const csrf = request.headers()["x-csrf-token"];
    backend.writes.push({ method, path, csrf, body });
    if (csrf !== CSRF) {
      return problem(route, 403, "CSRF_INVALID");
    }

    if (path === "/api/v1/cart/items" && method === "POST") {
      const product = PRODUCTS.find((p) => p.id === body.product_id);
      if (!product) return problem(route, 422, "PRODUCT_NOT_PURCHASABLE", { reason: "not_listed" });
      const reason = refusal(product);
      if (reason) return problem(route, 422, "PRODUCT_NOT_PURCHASABLE", { reason });
      const existing = backend.lines.find((line) => line.productId === product.id);
      const quantity = body.quantity ?? 1;
      if (product.type === "stl") {
        if (quantity !== 1) {
          return problem(route, 422, "QUANTITY_EXCEEDS_LIMIT", { max_quantity: 1, requested: quantity, current_quantity: existing?.quantity ?? 0 });
        }
        if (!existing) backend.lines.push({ productId: product.id, quantity: 1, snapshotCents: product.priceCents });
        return route.fulfill({ status: 200, body: JSON.stringify(cartRead(backend)) });
      }
      const merged = (existing?.quantity ?? 0) + quantity;
      if (product.maxQuantityPerLine !== null && merged > product.maxQuantityPerLine) {
        return problem(route, 422, "QUANTITY_EXCEEDS_LIMIT", {
          max_quantity: product.maxQuantityPerLine,
          requested: quantity,
          current_quantity: existing?.quantity ?? 0,
        });
      }
      if (existing) existing.quantity = merged;
      else backend.lines.push({ productId: product.id, quantity, snapshotCents: product.priceCents });
      return route.fulfill({ status: 200, body: JSON.stringify(cartRead(backend)) });
    }

    const productId = decodeURIComponent(path.split("/").pop()!);
    const line = backend.lines.find((l) => l.productId === productId);
    if (!line) return problem(route, 404, "NOT_FOUND");
    const product = PRODUCTS.find((p) => p.id === productId)!;

    if (method === "PATCH") {
      const reason = refusal(product);
      if (reason) return problem(route, 422, "PRODUCT_NOT_PURCHASABLE", { reason });
      const cap = product.type === "stl" ? 1 : product.maxQuantityPerLine;
      if (cap !== null && body.quantity > cap) {
        return problem(route, 422, "QUANTITY_EXCEEDS_LIMIT", { max_quantity: cap, requested: body.quantity, current_quantity: line.quantity });
      }
      line.quantity = body.quantity;
      return route.fulfill({ status: 200, body: JSON.stringify(cartRead(backend)) });
    }
    if (method === "DELETE") {
      backend.lines = backend.lines.filter((l) => l.productId !== productId);
      return route.fulfill({ status: 204, body: "" });
    }
    return problem(route, 405, "METHOD_NOT_ALLOWED");
  });

  return backend;
}

const header = (page: Page) => page.getByRole("banner");

test.describe("Cart (Phase 5C / FVS-025)", () => {
  test("an anonymous visit to /cart redirects to /login with a safe returnTo", async ({ page }) => {
    await page.goto("/cart");
    await expect(page).toHaveURL(/\/login\?returnTo=%2Fcart$/);
  });

  test("anonymous: Add to cart on a product page is a login link and sends no cart request", async ({ page }) => {
    const cartRequests: string[] = [];
    page.on("request", (request) => {
      if (new URL(request.url()).pathname.startsWith("/api/v1/cart")) cartRequests.push(request.url());
    });
    await page.route("**/api/v1/me", (route) =>
      route.fulfill({ status: 401, contentType: "application/problem+json", body: JSON.stringify({ status: 401, code: "AUTH_REQUIRED" }) })
    );
    await page.route("**/api/v1/auth/refresh", (route) =>
      route.fulfill({ status: 401, contentType: "application/problem+json", body: JSON.stringify({ status: 401, code: "AUTH_REQUIRED" }) })
    );
    await page.route(/\/api\/v1\/products\/dragon$/, (route) => route.fulfill({ body: JSON.stringify(productDetail(PRODUCTS[0]!)) }));

    await page.goto("/shop/dragon");
    await expect(page.getByRole("link", { name: "Add to cart" })).toHaveAttribute("href", "/login?returnTo=%2Fshop%2Fdragon");
    await expect(header(page).getByRole("link", { name: "Cart" })).toHaveAttribute("href", "/cart");
    expect(cartRequests).toEqual([]);
  });

  test("empty → add physical → reload → add STL → reload → change quantity → remove → reload → remove last → empty, every write exact and with CSRF", async ({
    page,
  }) => {
    const backend = await installFakeBackend(page);

    // Empty cart, reachable from the header.
    await page.goto("/");
    await header(page).getByRole("link", { name: "Cart" }).click();
    await expect(page).toHaveURL(/\/cart$/);
    await expect(page.getByText("Your cart is empty.")).toBeVisible();
    await expect(page.getByRole("link", { name: "Browse the shop" })).toHaveAttribute("href", "/shop");

    // Add a physical product with quantity 2 from its page.
    await page.goto("/shop/dragon");
    await page.getByRole("button", { name: "Increase quantity" }).click();
    await page.getByRole("button", { name: "Add to cart" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Added to your cart." })).toBeVisible();
    await expect(header(page).getByRole("link", { name: "Cart, 2 items" })).toBeVisible();
    expect(backend.writes.at(-1)).toEqual({
      method: "POST",
      path: "/api/v1/cart/items",
      csrf: CSRF,
      body: { product_id: "p-dragon", quantity: 2 },
    });

    await page.getByRole("link", { name: "View cart" }).click();
    await expect(page.getByRole("link", { name: "Articulated Dragon" })).toBeVisible();
    await page.reload();
    const dragon = page.getByRole("article", { name: "Articulated Dragon" });
    await expect(dragon.getByRole("group", { name: "Quantity of Articulated Dragon" })).toContainText("2");

    // Add an STL: no quantity control, always quantity 1.
    await page.goto("/shop/dragon-stl");
    await expect(page.getByRole("button", { name: /quantity/i })).toHaveCount(0);
    await page.getByRole("button", { name: "Add to cart" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Added to your cart." })).toBeVisible();
    expect(backend.writes.at(-1)?.body).toEqual({ product_id: "p-dragon-stl", quantity: 1 });

    await page.goto("/cart");
    await page.reload();
    const stl = page.getByRole("article", { name: "Dragon STL" });
    await expect(stl).toBeVisible();
    await expect(stl.getByText("STL files are sold one copy per order.")).toBeVisible();
    await expect(stl.getByRole("button", { name: /quantity/i })).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Cart summary" })).toContainText("3 items");
    await expect(page.getByRole("region", { name: "Cart summary" })).not.toContainText("$");

    // Physical quantity: absolute PATCH, then + disabled at the server cap (3).
    await dragon.getByRole("button", { name: "Increase quantity of Articulated Dragon" }).click();
    await expect(dragon.getByRole("group", { name: "Quantity of Articulated Dragon" })).toContainText("3");
    expect(backend.writes.at(-1)).toEqual({
      method: "PATCH",
      path: "/api/v1/cart/items/p-dragon",
      csrf: CSRF,
      body: { quantity: 3 },
    });
    await expect(dragon.getByRole("button", { name: "Increase quantity of Articulated Dragon" })).toBeDisabled();
    await expect(dragon.getByText("Maximum 3 per order")).toBeVisible();

    // Remove the STL line; reload proves the server state.
    await stl.getByRole("button", { name: "Remove Dragon STL from cart" }).click();
    await expect(page.getByRole("article", { name: "Dragon STL" })).toHaveCount(0);
    await expect(page.getByRole("heading", { level: 1, name: "Your cart" })).toBeFocused();
    expect(backend.writes.at(-1)).toEqual({ method: "DELETE", path: "/api/v1/cart/items/p-dragon-stl", csrf: CSRF, body: undefined });
    await page.reload();
    await expect(page.getByRole("article", { name: "Dragon STL" })).toHaveCount(0);
    await expect(page.getByRole("article", { name: "Articulated Dragon" })).toBeVisible();

    // Remove the last line → empty state.
    await page.getByRole("button", { name: "Remove Articulated Dragon from cart" }).click();
    await expect(page.getByText("Your cart is empty.")).toBeVisible();
    await page.reload();
    await expect(page.getByText("Your cart is empty.")).toBeVisible();
    await expect(header(page).getByRole("link", { name: "Cart" })).toBeVisible();
  });

  test("a merge above the cap is refused by the server and explained with its numbers", async ({ page }) => {
    const backend = await installFakeBackend(page, [{ productId: "p-dragon", quantity: 2, snapshotCents: 1800 }]);
    await page.goto("/shop/dragon");
    await page.getByRole("button", { name: "Increase quantity" }).click();
    await page.getByRole("button", { name: "Add to cart" }).click();

    // Scoped by text: Next's own route announcer is also role="alert".
    const alert = page.getByRole("alert").filter({ hasText: "at most" });
    await expect(alert).toHaveText("You can have at most 3 of this product in your cart. You already have 2.");
    await expect(page.getByText("RAW DETAIL")).toHaveCount(0);
    expect(backend.lines).toEqual([{ productId: "p-dragon", quantity: 2, snapshotCents: 1800 }]);
  });

  test("WhatsApp-only and unavailable products offer no cart action and send no cart write", async ({ page }) => {
    const backend = await installFakeBackend(page);

    await page.goto("/shop/moon-lamp");
    await expect(page.getByRole("heading", { level: 1, name: "Moon Lamp" })).toBeVisible();
    await expect(page.getByRole("link", { name: /chat on whatsapp/i })).toBeVisible();
    await expect(page.getByRole("button", { name: "Add to cart" })).toHaveCount(0);

    await page.goto("/shop/spiral-vase");
    await expect(page.getByText(/currently unavailable/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Add to cart" })).toHaveCount(0);

    expect(backend.writes).toEqual([]);
  });

  test("lines the server flags as unpurchasable or price-changed are explained; the unpurchasable one can only be removed", async ({
    page,
  }) => {
    // The vase became unavailable after it was added; the dragon's price
    // rose from 15.00 to 18.00 since it was added.
    await installFakeBackend(page, [
      { productId: "p-vase", quantity: 1, snapshotCents: 2200 },
      { productId: "p-dragon", quantity: 1, snapshotCents: 1500 },
    ]);
    await page.goto("/cart");

    const vase = page.getByRole("article", { name: "Spiral Vase" });
    await expect(vase.getByText(/currently unavailable\. remove it to check out/i)).toBeVisible();
    await expect(vase.getByRole("button", { name: /quantity/i })).toHaveCount(0);
    await expect(vase.getByRole("button", { name: "Remove Spiral Vase from cart" })).toBeEnabled();

    const dragon = page.getByRole("article", { name: "Articulated Dragon" });
    await expect(dragon.getByText("$15.00")).toBeVisible();
    await expect(dragon.getByText("$18.00")).toBeVisible();
    await expect(dragon.getByText(/price has changed since you added it/i)).toBeVisible();
    await expect(page.getByText(/some items need your attention/i)).toBeVisible();
    await expect(page.getByText(/checkout isn't available yet/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /checkout/i })).toHaveCount(0);
  });

  test("a CSRF rejection shows safe copy and leaves the cart unchanged", async ({ page }) => {
    const backend = await installFakeBackend(page, [{ productId: "p-dragon", quantity: 1, snapshotCents: 1800 }]);
    await page.context().addCookies([{ name: "csrf_token", value: "stale-value", url: "http://localhost:3000" }]);
    await page.goto("/cart");

    const dragon = page.getByRole("article", { name: "Articulated Dragon" });
    await dragon.getByRole("button", { name: "Increase quantity of Articulated Dragon" }).click();
    await expect(dragon.getByRole("alert")).toHaveText("Unable to verify your session. Please refresh the page and try again.");
    expect(backend.writes.at(-1)?.csrf).toBe("stale-value");
    expect(backend.lines[0]?.quantity).toBe(1);
    await expect(dragon.getByRole("group", { name: "Quantity of Articulated Dragon" })).toContainText("1");
  });

  test("a line removed elsewhere (404) is explained and the cart refreshes to server truth", async ({ page }) => {
    const backend = await installFakeBackend(page, [{ productId: "p-dragon", quantity: 1, snapshotCents: 1800 }]);
    await page.goto("/cart");
    await expect(page.getByRole("article", { name: "Articulated Dragon" })).toBeVisible();

    backend.lines = [];
    await page.getByRole("button", { name: "Remove Articulated Dragon from cart" }).click();

    await expect(page.getByText("Your cart is empty.")).toBeVisible();
    await expect(
      page.getByRole("alert").filter({ hasText: "This item is no longer in your cart. Your cart has been refreshed." })
    ).toBeVisible();
  });
});
