import type { Page } from "@playwright/test";

// Phase 5C — the header cart link reads GET /api/v1/cart on every page
// for a signed-in viewer. Specs that mock a signed-in /me (but are not
// about the cart) register this so that read never leaves the browser:
// mocked E2E must not depend on :8000. Exact path only, so it can never
// intercept /api/v1/cart/items or any catalogue request. A route a test
// registers later takes precedence (Playwright runs the newest handler
// first), so cart.spec.ts's own fake backend overrides it.
export const EMPTY_CART = {
  id: null,
  items: [],
  contains_physical: false,
  contains_digital: false,
  updated_at: null,
};

export async function stubEmptyCart(page: Page): Promise<void> {
  await stubEmptyWishlist(page);
  await page.route(/\/api\/v1\/cart$/, (route) =>
    route.request().method() === "GET"
      ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(EMPTY_CART) })
      : route.fallback()
  );
}

// Phase 6D — product cards and the product page read the signed-in
// viewer's wishlist (GET /api/v1/me/wishlist?limit=100). Specs that sign a
// viewer in through stubEmptyCart get an empty wishlist too, so that read
// never leaves the browser either. GET only, exact path; wishlist.spec.ts
// registers its own fake later, which takes precedence.
export async function stubEmptyWishlist(page: Page): Promise<void> {
  await page.route(/\/api\/v1\/me\/wishlist(\?.*)?$/, (route) =>
    route.request().method() === "GET"
      ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], next_cursor: null }) })
      : route.fallback()
  );
}
