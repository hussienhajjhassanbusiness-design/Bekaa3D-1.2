import { test, expect, type Page } from "@playwright/test";

// REAL STOREFRONT INTEGRATION — PHASE 1. Deterministic, backend-
// independent coverage for the real `/shop` catalogue, matching
// login-session.spec.ts's own precedent: route interception only, never a
// real backend. Fixture bodies are contract-shaped (openapi.json
// ProductListItem/ProductPage/CategoryList/ColourList/MaterialList/
// SearchSuggestionList), never an invented field.

const CATEGORY = { id: "cat-1", name: "Toys and Figures", slug: "toys-figures" };
const MATERIAL = { id: "mat-1", name: "PLA" };
const COLOUR = { id: "col-1", name: "Red" };

function productItem(overrides: Record<string, unknown> = {}) {
  return {
    id: "p1",
    type: "physical",
    name: "Articulated Dragon",
    slug: "dragon",
    cover_image: null,
    price: { amount_cents: 1800, currency: "USD" },
    category: CATEGORY,
    material: MATERIAL,
    colour: COLOUR,
    is_available: true,
    purchase_mode: "both",
    average_rating: 0,
    review_count: 0,
    is_featured: false,
    ...overrides,
  };
}

async function mockReferenceData(page: Page) {
  await page.route("**/api/v1/categories", (route) => route.fulfill({ body: JSON.stringify({ items: [CATEGORY] }) }));
  await page.route("**/api/v1/materials", (route) => route.fulfill({ body: JSON.stringify({ items: [MATERIAL] }) }));
  await page.route("**/api/v1/colours", (route) => route.fulfill({ body: JSON.stringify({ items: [COLOUR] }) }));
}

test.describe("Shop catalogue (/shop)", () => {
  test("loads and shows real products from the catalogue endpoint", async ({ page }) => {
    await mockReferenceData(page);
    await page.route("**/api/v1/products**", (route) =>
      route.fulfill({ body: JSON.stringify({ items: [productItem()], next_cursor: null }) })
    );

    await page.goto("/shop");

    await expect(page.getByRole("link", { name: /Articulated Dragon/ })).toBeVisible();
    await expect(page.getByText("$18.00")).toBeVisible();
  });

  test("selecting a category filter updates the URL to category_id's frontend key and refetches", async ({ page }) => {
    await mockReferenceData(page);
    let lastUrl = "";
    await page.route("**/api/v1/products**", (route) => {
      lastUrl = route.request().url();
      route.fulfill({ body: JSON.stringify({ items: [productItem()], next_cursor: null }) });
    });

    await page.goto("/shop");
    await expect(page.getByRole("link", { name: /Articulated Dragon/ })).toBeVisible();
    // A plain click, not .check(): checking the box triggers a client-side
    // URL navigation that re-renders this exact checkbox element from
    // fresh data, so the URL (the real source of truth here, per
    // ShopView's "URL state is the source of truth" design) is the
    // correct thing to assert on — not Playwright's own built-in
    // before/after checked-attribute comparison on a node that gets
    // re-rendered out from under it.
    await page.getByRole("checkbox", { name: "Toys and Figures" }).click();

    await expect(page).toHaveURL(/category=cat-1/);
    await expect.poll(() => lastUrl).toContain("category_id=cat-1");
    await expect(page.getByRole("checkbox", { name: "Toys and Figures" })).toBeChecked();
  });

  test("shows the empty state with a clear-filters action when no products match", async ({ page }) => {
    await mockReferenceData(page);
    await page.route("**/api/v1/products**", (route) =>
      route.fulfill({ body: JSON.stringify({ items: [], next_cursor: null }) })
    );

    await page.goto("/shop?category=cat-1");

    await expect(page.getByText(/no products match your filters/i)).toBeVisible();
    // Two "Clear filters" controls legitimately coexist here (the filter
    // sidebar's own clear-all, and the empty state's contextual action) —
    // both call the same handler, so either is a valid interaction target.
    await page.getByRole("button", { name: /clear filters/i }).first().click();
    // The app pushes "/shop?" (an explicit, empty query string) — real
    // browsers normalize away a bare trailing "?" with nothing after it,
    // so the committed URL reads "/shop".
    await expect(page).toHaveURL("/shop");
  });

  test("Load more fetches the next cursor page and appends results", async ({ page }) => {
    await mockReferenceData(page);
    await page.route("**/api/v1/products**", (route) => {
      const url = new URL(route.request().url());
      const cursor = url.searchParams.get("cursor");
      if (cursor === "page-2-token") {
        route.fulfill({
          body: JSON.stringify({ items: [productItem({ id: "p2", slug: "knight", name: "Articulated Knight" })], next_cursor: null }),
        });
      } else {
        route.fulfill({ body: JSON.stringify({ items: [productItem()], next_cursor: "page-2-token" }) });
      }
    });

    await page.goto("/shop");
    await expect(page.getByRole("link", { name: /Articulated Dragon/ })).toBeVisible();

    await page.getByRole("button", { name: /load more/i }).click();

    await expect(page.getByRole("link", { name: /Articulated Knight/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /Articulated Dragon/ })).toBeVisible();
  });

  test("search suggestions appear after 3 characters and link to the real product-detail route", async ({ page }) => {
    await mockReferenceData(page);
    await page.route("**/api/v1/products**", (route) =>
      route.fulfill({ body: JSON.stringify({ items: [], next_cursor: null }) })
    );
    await page.route("**/api/v1/search/suggestions**", (route) =>
      route.fulfill({
        body: JSON.stringify({ items: [{ id: "p1", name: "Articulated Dragon", slug: "dragon", type: "physical" }] }),
      })
    );

    await page.goto("/shop");
    const searchInput = page.getByLabel(/search products/i);
    await searchInput.fill("dr");
    await expect(page.getByRole("button", { name: /Articulated Dragon/ })).toHaveCount(0);

    await searchInput.fill("dra");
    const suggestionLink = page.getByRole("button", { name: /Articulated Dragon/ });
    await expect(suggestionLink).toBeVisible();
    await suggestionLink.click();
    await expect(page).toHaveURL("/shop/dragon");
  });

  test("shows a retryable error state when the catalogue fails to load", async ({ page }) => {
    await mockReferenceData(page);
    await page.route("**/api/v1/products**", (route) => route.fulfill({ status: 500, body: "{}" }));

    await page.goto("/shop");

    // The grid retries a few times with TanStack's default backoff before
    // settling into the error state — allow real time for that, beyond
    // the default 5s assertion timeout.
    await expect(page.getByRole("alert").filter({ hasText: /couldn.t load products/i })).toBeVisible({
      timeout: 15_000,
    });
  });
});
