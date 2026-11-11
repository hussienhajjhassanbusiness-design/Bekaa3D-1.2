import { test, expect, type Page } from "@playwright/test";
import { stubEmptyCart } from "./support/stubCart";

// Phase 5C: keep the header cart read inside the browser (no :8000).
test.beforeEach(async ({ page }) => {
  await stubEmptyCart(page);
});

// Phase 3 (P1-1/FVS-005) — the admin guard decision table, proven end to
// end against a real browser/cookie jar via route interception (never a
// real backend — see login-session.spec.ts / account-profile.spec.ts for
// the same established pattern). Four outcomes:
//   no session -> /login; signed-in customer -> real 404 (never an
//   "admin area exists here" leak); admin with MFA complete -> the real
//   admin shell; admin whose MFA enrolment is incomplete -> redirected to
//   /admin/mfa/setup the moment any admin API call answers
//   401 MFA_REQUIRED.

interface RawMeBody {
  id: string;
  email: string;
  role: string;
  email_verified: boolean;
  email_verified_at: string | null;
  created_at: string;
}

const ADMIN_ME: RawMeBody = {
  id: "admin-1",
  email: "admin@example.com",
  role: "admin",
  email_verified: true,
  email_verified_at: "2025-01-01T00:00:00Z",
  created_at: "2024-01-01T00:00:00Z",
};

const CUSTOMER_ME: RawMeBody = { ...ADMIN_ME, id: "customer-1", email: "customer@example.com", role: "customer" };

async function signInAs(page: Page, meBody: RawMeBody) {
  await page.context().addCookies([{ name: "csrf_token", value: "test-value", url: "http://localhost:3000" }]);
  await page.route("**/api/v1/me", async (route) => {
    await route.fulfill({ status: 200, body: JSON.stringify(meBody) });
  });
}

const EMPTY_SETTINGS_PAGE = { items: [], next_cursor: null };

test.describe("Admin guard (P1-1)", () => {
  test("an unauthenticated visit to /admin/settings redirects to /login with a returnTo", async ({ page }) => {
    await page.route("**/api/v1/me", async (route) => {
      await route.fulfill({ status: 401, body: JSON.stringify({ code: "AUTH_REQUIRED" }) });
    });

    await page.goto("/admin/settings");

    await expect(page).toHaveURL(/\/login\?returnTo=%2Fadmin%2Fsettings/);
  });

  test("a signed-in customer visiting /admin/settings sees the real 404 page, never an admin-exists-here message", async ({
    page,
  }) => {
    await signInAs(page, CUSTOMER_ME);

    await page.goto("/admin/settings");

    await expect(page.getByText(/404/)).toBeVisible();
    expect(page.url()).toContain("/admin/settings");
    const bodyText = await page.evaluate(() => document.body.innerText);
    expect(bodyText.toLowerCase()).not.toContain("admin");
  });

  test("an administrator with MFA already complete sees the real admin shell and settings content", async ({ page }) => {
    await signInAs(page, ADMIN_ME);
    await page.route("**/api/v1/admin/settings*", async (route) => {
      await route.fulfill({ status: 200, body: JSON.stringify(EMPTY_SETTINGS_PAGE) });
    });

    await page.goto("/admin/settings");

    await expect(page.getByRole("navigation", { name: "Admin" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  });

  test("an administrator whose MFA enrolment is incomplete is redirected to /admin/mfa/setup the moment the settings call answers MFA_REQUIRED", async ({
    page,
  }) => {
    await signInAs(page, ADMIN_ME);
    await page.route("**/api/v1/admin/settings*", async (route) => {
      await route.fulfill({ status: 401, body: JSON.stringify({ code: "MFA_REQUIRED" }) });
    });

    await page.goto("/admin/settings");

    await expect(page).toHaveURL(/\/admin\/mfa\/setup$/);
  });

  test("the admin nav never links to an unbuilt area (contact/shipping/etc.; orders since 5H, payments and refunds since 5I)", async ({ page }) => {
    await signInAs(page, ADMIN_ME);
    await page.route("**/api/v1/admin/settings*", async (route) => {
      await route.fulfill({ status: 200, body: JSON.stringify(EMPTY_SETTINGS_PAGE) });
    });

    await page.goto("/admin/settings");

    const nav = page.getByRole("navigation", { name: "Admin" });
    await expect(nav).toBeVisible();
    const navText = (await nav.innerText()).toLowerCase();
    for (const forbidden of ["cancellation", "contact", "shipping", "entitlement"]) {
      expect(navText).not.toContain(forbidden);
    }
    await expect(nav.getByRole("link", { name: "Orders" })).toHaveAttribute("href", "/admin/orders");
  });
});
