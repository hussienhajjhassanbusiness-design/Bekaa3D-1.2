import type { Page } from "@playwright/test";

// Phase 6E — every page mounts AuthProvider, which reads GET /api/v1/me
// (and, on a 401, tries POST /api/v1/auth/refresh). Specs that are about an
// anonymous visitor register this so those reads never leave the browser:
// mocked E2E must not depend on whether :8000 is up. A route a test
// registers later takes precedence (Playwright runs the newest handler
// first), so a test that signs a viewer in still overrides it.
const AUTH_REQUIRED = {
  status: 401,
  contentType: "application/problem+json",
  body: JSON.stringify({ type: "about:blank", title: "Unauthorized", status: 401, code: "AUTH_REQUIRED", errors: [] }),
};

export async function stubGuest(page: Page): Promise<void> {
  await page.route(/\/api\/v1\/me$/, (route) => route.fulfill(AUTH_REQUIRED));
  await page.route(/\/api\/v1\/auth\/refresh$/, (route) => route.fulfill(AUTH_REQUIRED));
}
