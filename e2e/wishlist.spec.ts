import { test, expect, type Page, type Route } from "@playwright/test";
import { stubEmptyCart } from "./support/stubCart";

// Phase 6D — Wishlist against a deterministic stand-in for backend 2dfb27b
// (engagement/api/wishlist.py): GET /api/v1/me/wishlist (cursor pages),
// PUT/DELETE /api/v1/me/wishlist/{product_id} (204, idempotent, CSRF).
// Route interception only: no backend on :8000, no media server on :8001.

type Json = Record<string, unknown>;
const uuid = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const CUSTOMER_ME = { id: uuid(901), email: "rana@example.com", role: "customer", email_verified: true, email_verified_at: "2025-01-01T00:00:00Z", created_at: "2024-01-01T00:00:00Z" };
const OTHER_ME = { ...CUSTOMER_ME, id: uuid(902), email: "sami@example.com" };
const CATEGORY = { id: "cat-1", name: "Toys and Figures", slug: "toys-figures" };
const DRAGON = uuid(501);
const VASE = uuid(502);

function listItem(id: string, name: string, slug: string, type: "physical" | "stl", cents: number): Json {
  return { id, type, name, slug, cover_image: null, price: { amount_cents: cents, currency: "USD" }, category: CATEGORY, material: null, colour: null, is_available: true, purchase_mode: type === "stl" ? null : "both", average_rating: 0, review_count: 0, is_featured: false };
}
const PRODUCTS = [listItem(DRAGON, "Articulated Dragon", "dragon", "physical", 1800), listItem(VASE, "Low Poly Vase STL", "vase-stl", "stl", 400)];
const DETAIL = {
  ...PRODUCTS[0],
  description: null, images: [], seo_title: null, seo_description: null, og_image_url: null, dimensions: null,
  production_lead_time_days: null, batch_size: null, max_quantity_per_line: 5,
  capabilities: { can_add_to_cart: true, can_offer: false, whatsapp_available: false },
};

function problem(status: number, code: string) {
  return { status, contentType: "application/problem+json", body: JSON.stringify({ type: "about:blank", title: "RAW TITLE", status, detail: "RAW DETAIL", code, errors: [] }) };
}

interface Fake {
  // productId -> saved item, per user id (the server's per-user rows).
  saved: Map<string, Json[]>;
  user: Json | null;
  writes: { method: string; path: string; csrf: string | null }[];
  failNext: ReturnType<typeof problem> | null;
  pageSize: number;
}

function wishItem(id: string, available = true): Json {
  const p = PRODUCTS.find((x) => x.id === id)!;
  return available
    ? { product_id: id, created_at: "2026-11-12T10:00:00Z", available: true, name: p.name, slug: p.slug, type: p.type, price_cents: (p.price as Json).amount_cents, currency: "USD" }
    : { product_id: id, created_at: "2026-11-12T10:00:00Z", available: false, name: p.name, slug: null, type: null, price_cents: null, currency: null };
}

async function install(page: Page, user: Json | null): Promise<Fake> {
  const fake: Fake = { saved: new Map(), user, writes: [], failNext: null, pageSize: 100 };
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  await page.context().addCookies([{ name: "csrf_token", value: "e2e-csrf-value", url: "http://localhost:3000" }]);
  await stubEmptyCart(page);
  await page.route(/\/api\/v1\/me$/, (r) => (fake.user ? json(r, fake.user) : r.fulfill(problem(401, "AUTH_REQUIRED"))));
  await page.route(/\/api\/v1\/auth\/refresh$/, (r) => r.fulfill(problem(401, "AUTH_REQUIRED")));
  await page.route(/\/api\/v1\/auth\/logout$/, (r) => {
    fake.user = null;
    return r.fulfill({ status: 204, body: "" });
  });
  await page.route(/\/api\/v1\/settings\/public$/, (r) =>
    json(r, { accepting_orders: true, cash_payment_enabled: false, cash_max_order_total: null, pickup_address: null, pickup_hours: null, whatsapp_number: null })
  );
  await page.route(/\/api\/v1\/(categories|materials|colours)$/, (r) => json(r, { items: [] }));
  await page.route(/\/api\/v1\/products(\?.*)?$/, (r) => json(r, { items: PRODUCTS, next_cursor: null }));
  await page.route(/\/api\/v1\/products\/dragon$/, (r) => json(r, DETAIL));
  await page.route(/\/api\/v1\/notifications(\?.*)?$/, (r) => json(r, { items: [], next_cursor: null, unread_count: 0 }));
  await page.route(/\/api\/v1\/me\/wishlist(\?.*)?$/, (route) => {
    if (!fake.user) return route.fulfill(problem(401, "AUTH_REQUIRED"));
    const url = new URL(route.request().url());
    const all = fake.saved.get(fake.user.id as string) ?? [];
    const start = Number(url.searchParams.get("cursor") ?? "0");
    const page = all.slice(start, start + fake.pageSize);
    const next = start + fake.pageSize < all.length ? String(start + fake.pageSize) : null;
    return json(route, { items: page, next_cursor: next });
  });
  await page.route(/\/api\/v1\/me\/wishlist\/[^/?]+$/, (route) => {
    const r = route.request();
    const id = new URL(r.url()).pathname.split("/").pop()!;
    fake.writes.push({ method: r.method(), path: new URL(r.url()).pathname, csrf: r.headers()["x-csrf-token"] ?? null });
    if (fake.failNext) {
      const f = fake.failNext;
      fake.failNext = null;
      return route.fulfill(f);
    }
    const key = fake.user!.id as string;
    const list = fake.saved.get(key) ?? [];
    if (r.method() === "PUT" && !list.some((x) => x.product_id === id)) list.unshift(wishItem(id));
    const at = list.findIndex((x) => x.product_id === id);
    if (r.method() === "DELETE" && at >= 0) list.splice(at, 1);
    fake.saved.set(key, list);
    return route.fulfill({ status: 204, body: "" });
  });
  return fake;
}

async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

const heart = (page: Page, name: string) => page.getByRole("button", { name: `Save ${name} to your wishlist` });

test.describe("Wishlist (Phase 6D)", () => {
  test("anonymous: hearts are sign-in links and no wishlist request is sent", async ({ page }) => {
    const reads: string[] = [];
    page.on("request", (req) => {
      if (new URL(req.url()).pathname.startsWith("/api/v1/me/wishlist")) reads.push(req.url());
    });
    await install(page, null);
    await page.goto("/shop");
    await expect(page.getByRole("link", { name: "Sign in to save Articulated Dragon to your wishlist" })).toHaveAttribute(
      "href",
      "/login?returnTo=%2Fshop%2Fdragon"
    );
    await page.goto("/shop/dragon");
    await expect(page.getByRole("link", { name: "Save to wishlist" })).toHaveAttribute("href", "/login?returnTo=%2Fshop%2Fdragon");
    expect(reads).toEqual([]);
  });

  test("add from a card, synchronized with the product page and the account wishlist; remove; reload", async ({ page }) => {
    const fake = await install(page, CUSTOMER_ME);
    await page.goto("/shop");
    await expect(heart(page, "Articulated Dragon")).toHaveAttribute("aria-pressed", "false");
    await heart(page, "Articulated Dragon").click();
    await expect(heart(page, "Articulated Dragon")).toHaveAttribute("aria-pressed", "true");
    await expect(heart(page, "Low Poly Vase STL")).toHaveAttribute("aria-pressed", "false");
    expect(fake.writes).toEqual([{ method: "PUT", path: `/api/v1/me/wishlist/${DRAGON}`, csrf: "e2e-csrf-value" }]);

    await page.getByRole("link", { name: /Articulated Dragon/ }).first().click();
    await expect(page).toHaveURL(/\/shop\/dragon$/);
    await expect(page.getByRole("button", { name: "Remove from wishlist" })).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: "Saved to your wishlist." })).toBeVisible();

    await page.goto("/account/wishlist");
    await expect(page.getByRole("heading", { level: 1, name: "Wishlist" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Articulated Dragon" })).toHaveAttribute("href", "/shop/dragon");
    await page.reload();
    await expect(page.getByRole("link", { name: "Articulated Dragon" })).toBeVisible();

    await page.getByRole("button", { name: "Remove Articulated Dragon from your wishlist" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Removed Articulated Dragon from your wishlist." })).toBeVisible();
    await expect(page.getByText(/Your wishlist is empty/)).toBeVisible();
    expect(fake.writes.at(-1)).toEqual({ method: "DELETE", path: `/api/v1/me/wishlist/${DRAGON}`, csrf: "e2e-csrf-value" });

    await page.goto("/shop");
    await expect(heart(page, "Articulated Dragon")).toHaveAttribute("aria-pressed", "false");
  });

  test("a CSRF refusal keeps the state and shows safe copy", async ({ page }) => {
    const fake = await install(page, CUSTOMER_ME);
    fake.failNext = problem(403, "CSRF_INVALID");
    await page.goto("/shop/dragon");
    await page.getByRole("button", { name: "Save to wishlist" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "Unable to verify your session" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Save to wishlist" })).toBeVisible();
    await expect(page.getByText(/RAW/)).toHaveCount(0);
  });

  test("an unavailable item stays listed by name with only Remove; every page of the list is read", async ({ page }) => {
    const fake = await install(page, CUSTOMER_ME);
    fake.pageSize = 1;
    fake.saved.set(CUSTOMER_ME.id, [wishItem(VASE, false), wishItem(DRAGON)]);
    const reads: string[] = [];
    page.on("request", (req) => {
      if (new URL(req.url()).pathname === "/api/v1/me/wishlist") reads.push(new URL(req.url()).search);
    });
    await page.goto("/account/wishlist");
    const row = page.getByRole("listitem").filter({ hasText: "Low Poly Vase STL" });
    await expect(row.getByText("No longer available")).toBeVisible();
    await expect(row.getByRole("link")).toHaveCount(0);
    await expect(row.getByRole("button", { name: "Remove Low Poly Vase STL from your wishlist" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Articulated Dragon" })).toBeVisible();
    expect(reads.slice(0, 2)).toEqual(["?limit=100", "?limit=100&cursor=1"]);
  });

  test("logout and a different user never see the previous user's wishlist", async ({ page }) => {
    const fake = await install(page, CUSTOMER_ME);
    fake.saved.set(CUSTOMER_ME.id, [wishItem(DRAGON)]);
    await page.goto("/account/wishlist");
    await expect(page.getByRole("link", { name: "Articulated Dragon" })).toBeVisible();
    await page.getByRole("button", { name: "Log out" }).first().click();
    await expect(page).toHaveURL(/\/login/);

    fake.user = OTHER_ME;
    await page.goto("/shop");
    await expect(heart(page, "Articulated Dragon")).toHaveAttribute("aria-pressed", "false");
    await page.goto("/account/wishlist");
    await expect(page.getByText(/Your wishlist is empty/)).toBeVisible();
  });

  test("keyboard and mobile: the heart toggles with Enter and keeps focus; no horizontal scroll", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 740 });
    await install(page, CUSTOMER_ME);
    await page.goto("/shop");
    const h = heart(page, "Low Poly Vase STL");
    await h.focus();
    await page.keyboard.press("Enter");
    await expect(h).toHaveAttribute("aria-pressed", "true");
    await expect(h).toBeFocused();
    await noHorizontalScroll(page);
    await page.goto("/account/wishlist");
    await expect(page.getByRole("link", { name: "Low Poly Vase STL" })).toBeVisible();
    await noHorizontalScroll(page);
  });
});
