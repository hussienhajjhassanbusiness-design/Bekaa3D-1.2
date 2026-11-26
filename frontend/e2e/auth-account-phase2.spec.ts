import { test, expect, type Page } from "@playwright/test";
import { E2E_CAPTCHA_TOKEN, routeFakeTurnstile, waitForCaptchaToken } from "./support/fakeTurnstile";
import { stubEmptyCart } from "./support/stubCart";
import { E2E_ORIGIN } from "./support/origin";

// Phase 5C: keep the header cart read inside the browser (no :8000).
test.beforeEach(async ({ page }) => {
  await stubEmptyCart(page);
});

// REAL CUSTOMER / AUTH / ACCOUNT INTEGRATION — PHASE 2. Three deterministic,
// backend-independent E2E specs covering the newly mounted routes
// (/forgot-password, /reset-password, /account/notifications), added to
// the existing "smoke" project (see playwright.config.ts). Route
// interception only, same precedent as register-and-verify.spec.ts and
// account-profile.spec.ts — never a real backend.

const TEST_TOKEN = "a".repeat(40);

test.describe("Forgot password (Phase 2 / FVS-004 request half)", () => {
  test("request -> enumeration-safe success, identical copy regardless of account existence", async ({ page }) => {
    await routeFakeTurnstile(page);
    let requestBody: unknown;
    await page.route("**/api/v1/auth/password-reset/request", async (route) => {
      requestBody = route.request().postDataJSON();
      await route.fulfill({
        status: 202,
        body: JSON.stringify({ message: "If an account exists for that address, a reset email has been sent." }),
      });
    });

    await page.goto("/forgot-password");
    await waitForCaptchaToken(page);
    await page.getByLabel(/email/i).fill("ada@example.com");
    await page.getByRole("button", { name: /send reset link/i }).click();

    await expect(page.getByText(/if an account exists/i)).toBeVisible();
    expect(requestBody).toEqual({ email: "ada@example.com", captcha_token: E2E_CAPTCHA_TOKEN });
  });
});

test.describe("Reset password (Phase 2 / FVS-004 confirm half)", () => {
  test("token in URL fragment -> sanitized from the address bar -> submit -> success -> Log in returns to /login", async ({
    page,
  }) => {
    let confirmBody: unknown;
    await page.route("**/api/v1/auth/password-reset/confirm", async (route) => {
      confirmBody = route.request().postDataJSON();
      await route.fulfill({ status: 204, body: "" });
    });

    await page.goto(`/reset-password#token=${TEST_TOKEN}`);

    // The token must never linger in the visible URL after capture.
    await expect.poll(() => page.url()).not.toContain("token=");

    await page.getByLabel(/new password/i).fill("brand-new-password-1");
    await page.getByRole("button", { name: /reset password/i }).click();

    await expect(page.getByText(/password has been reset/i)).toBeVisible();
    expect(confirmBody).toEqual({ token: TEST_TOKEN, new_password: "brand-new-password-1" });

    // A successful reset never establishes a session — the user is sent
    // to /login by their own action, not auto-authenticated.
    await page.getByRole("button", { name: /log in/i }).click();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("a missing token shows an invalid-link state with a link back to /forgot-password", async ({ page }) => {
    await page.goto("/reset-password");

    await expect(page.getByText(/invalid/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /request a new/i })).toHaveAttribute("href", "/forgot-password");
  });

  test("an expired (410) token shows an expiry-specific message distinct from the generic invalid-link copy", async ({
    page,
  }) => {
    await page.route("**/api/v1/auth/password-reset/confirm", async (route) => {
      await route.fulfill({
        status: 410,
        contentType: "application/problem+json",
        body: JSON.stringify({ type: "about:blank", title: "Gone", status: 410, detail: "expired", instance: "/x" }),
      });
    });

    await page.goto(`/reset-password#token=${TEST_TOKEN}`);
    await page.getByLabel(/new password/i).fill("brand-new-password-1");
    await page.getByRole("button", { name: /reset password/i }).click();

    await expect(page.getByText(/expired/i)).toBeVisible();
  });
});

async function signInAs(page: Page) {
  await page.context().addCookies([{ name: "csrf_token", value: "test-csrf-value", url: E2E_ORIGIN }]);
  await page.route("**/api/v1/me", async (route) => {
    await route.fulfill({
      status: 200,
      body: JSON.stringify({
        id: "u-1",
        email: "ada@example.com",
        role: "customer",
        email_verified: true,
        email_verified_at: "2025-01-01T00:00:00Z",
        created_at: "2024-01-01T00:00:00Z",
      }),
    });
  });
}

test.describe("Account notifications (Phase 2 / FVS-008)", () => {
  test("list renders real notifications, pagination via next_cursor, and mark-read sends X-CSRF-Token", async ({
    page,
  }) => {
    await signInAs(page);

    let listCallCount = 0;
    await page.route("**/api/v1/me/notifications*", async (route) => {
      const url = new URL(route.request().url());
      if (route.request().method() === "GET") {
        listCallCount += 1;
        if (!url.searchParams.has("cursor")) {
          await route.fulfill({
            status: 200,
            body: JSON.stringify({
              items: [
                { id: "n1", type: "account", payload: {}, read: false, created_at: "2026-01-01T00:00:00Z" },
              ],
              next_cursor: "page-2",
            }),
          });
        } else {
          await route.fulfill({
            status: 200,
            body: JSON.stringify({
              items: [
                { id: "n2", type: "order", payload: { event: "order.created" }, read: false, created_at: "2026-01-02T00:00:00Z" },
              ],
              next_cursor: null,
            }),
          });
        }
      } else {
        await route.continue();
      }
    });

    let patchHeader: string | null = null;
    let patchBody: unknown;
    await page.route("**/api/v1/me/notifications/n1", async (route) => {
      patchHeader = route.request().headers()["x-csrf-token"] ?? null;
      patchBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        body: JSON.stringify({ id: "n1", type: "account", payload: {}, read: true, created_at: "2026-01-01T00:00:00Z" }),
      });
    });

    await page.goto("/account/notifications");

    await expect(page.getByText(/unread/i).first()).toBeVisible();
    await page.getByRole("button", { name: /load more/i }).click();
    await expect(page.getByText(/order update: order\.created/i)).toBeVisible();
    expect(listCallCount).toBe(2);

    await page.getByRole("button", { name: /mark read/i }).first().click();
    await expect.poll(() => patchHeader).toBe("test-csrf-value");
    expect(patchBody).toEqual({ read: true });
  });

  test("an anonymous visit to /account/notifications redirects to /login", async ({ page }) => {
    await page.route("**/api/v1/me", async (route) => {
      await route.fulfill({
        status: 401,
        contentType: "application/problem+json",
        body: JSON.stringify({
          type: "about:blank",
          title: "Unauthorized",
          status: 401,
          detail: "x",
          instance: "/api/v1/me",
          code: "AUTH_REQUIRED",
        }),
      });
    });

    await page.goto("/account/notifications");

    await expect(page).toHaveURL(/\/login/);
  });
});
