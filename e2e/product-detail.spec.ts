import { test, expect, type Page } from "@playwright/test";
import { stubGuest } from "./support/stubGuest";

// REAL STOREFRONT INTEGRATION — PHASE 1. Deterministic, backend-
// independent coverage for `/shop/[slug]` — route interception only,
// matching login-session.spec.ts's own precedent.

const physicalDetail = {
  id: "p1",
  type: "physical",
  name: "Articulated Dragon",
  slug: "dragon",
  cover_image: { id: "img1", url: "/media/products/dragon.png", alt_text: "Articulated Dragon, view 1", is_cover: true },
  price: { amount_cents: 1800, currency: "USD" },
  category: { id: "c1", name: "Toys and Figures", slug: "toys-figures" },
  material: { id: "m1", name: "PLA" },
  colour: { id: "co1", name: "Red" },
  is_available: true,
  purchase_mode: "both",
  average_rating: 0,
  review_count: 0,
  is_featured: false,
  description: "A fully articulated dragon print.",
  images: [{ id: "img1", url: "/media/products/dragon.png", alt_text: "Articulated Dragon, view 1", is_cover: true }],
  seo_title: null,
  seo_description: null,
  og_image_url: null,
  dimensions: { length_mm: 120, width_mm: 80, height_mm: 60 },
  production_lead_time_days: 2,
  batch_size: 2,
  max_quantity_per_line: 5,
  capabilities: { can_add_to_cart: true, can_offer: false, whatsapp_available: true },
};

const stlDetail = {
  ...physicalDetail,
  type: "stl",
  slug: "dragon-stl",
  material: null,
  colour: null,
  purchase_mode: null,
  dimensions: null,
  production_lead_time_days: null,
  batch_size: null,
  max_quantity_per_line: null,
  capabilities: { can_add_to_cart: true, can_offer: true, whatsapp_available: false },
};

async function mockSettings(page: Page, whatsappNumber: string | null = "+96170000000") {
  await page.route("**/api/v1/settings/public", (route) =>
    route.fulfill({
      body: JSON.stringify({
        accepting_orders: true,
        cash_payment_enabled: true,
        cash_max_order_total: { amount_cents: 10000, currency: "USD" },
        pickup_address: null,
        pickup_hours: null,
        whatsapp_number: whatsappNumber,
      }),
    })
  );
}

test.describe("Product detail (/shop/[slug])", () => {
  test.beforeEach(async ({ page }) => {
    await stubGuest(page);
  });

  test("renders a physical product's price, images, category/material/colour, and WhatsApp CTA", async ({ page }) => {
    await mockSettings(page);
    await page.route("**/api/v1/products/dragon", (route) => route.fulfill({ body: JSON.stringify(physicalDetail) }));

    await page.goto("/shop/dragon");

    await expect(page.getByRole("heading", { name: "Articulated Dragon" })).toBeVisible();
    await expect(page.getByText("$18.00")).toBeVisible();
    await expect(page.getByText("PLA", { exact: true })).toBeVisible();
    await expect(page.getByText("Red", { exact: true })).toBeVisible();
    const whatsappLink = page.getByRole("link", { name: /chat on whatsapp/i });
    await expect(whatsappLink).toBeVisible();
    await expect(whatsappLink).toHaveAttribute("href", /wa\.me\/96170000000/);
    await expect(whatsappLink).toHaveAttribute("href", /Articulated%20Dragon|Articulated\+Dragon/);
  });

  test("renders an STL product without showing empty labels for its null physical-only fields", async ({ page }) => {
    await mockSettings(page, null);
    await page.route("**/api/v1/products/dragon-stl", (route) => route.fulfill({ body: JSON.stringify(stlDetail) }));

    await page.goto("/shop/dragon-stl");

    await expect(page.getByRole("heading", { name: "Articulated Dragon" })).toBeVisible();
    // The type badge itself (exact text): the Batch 2 footer copy also
    // mentions "STL files".
    await expect(page.getByRole("main").getByText("STL", { exact: true })).toBeVisible();
    await expect(page.getByText(/material:/i)).toHaveCount(0);
    await expect(page.getByText(/colour:/i)).toHaveCount(0);
    await expect(page.getByRole("link", { name: /chat on whatsapp/i })).toHaveCount(0);
  });

  test("a hidden/nonexistent slug renders the app's real not-found page", async ({ page }) => {
    await mockSettings(page);
    await page.route("**/api/v1/products/does-not-exist", (route) =>
      route.fulfill({
        status: 404,
        contentType: "application/problem+json",
        body: JSON.stringify({
          type: "http://localhost:8000/problems/NOT_FOUND",
          title: "Request cannot be completed",
          status: 404,
          detail: "Not Found",
          instance: "/api/v1/products/does-not-exist",
          code: "NOT_FOUND",
          request_id: "req_test",
          errors: [],
        }),
      })
    );

    await page.goto("/shop/does-not-exist");

    await expect(page.getByRole("heading", { name: /page not found/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /back to home/i })).toHaveAttribute("href", "/");
  });

  test("shows the Unavailable notice for a currently-unavailable physical product, with no purchase CTA", async ({
    page,
  }) => {
    await mockSettings(page);
    await page.route("**/api/v1/products/knight", (route) =>
      route.fulfill({
        body: JSON.stringify({
          ...physicalDetail,
          slug: "knight",
          name: "Articulated Knight",
          is_available: false,
          capabilities: { can_add_to_cart: false, can_offer: false, whatsapp_available: false },
        }),
      })
    );

    await page.goto("/shop/knight");

    await expect(page.getByText(/currently unavailable/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /add to cart/i })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /chat on whatsapp/i })).toHaveCount(0);
  });
});
