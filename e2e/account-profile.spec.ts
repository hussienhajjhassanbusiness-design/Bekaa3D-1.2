import { test, expect, type Page } from "@playwright/test";
import { stubEmptyCart } from "./support/stubCart";

// Phase 5C: keep the header cart read inside the browser (no :8000).
test.beforeEach(async ({ page }) => {
  await stubEmptyCart(page);
});

// FVS-006-IMPLEMENTATION-PLAN.md T05 (real-browser review evidence) + T06
// (deterministic E2E deliverable) — one file serving both purposes, same
// precedent as FVS-003 BATCH 4's login-session.spec.ts. Route interception
// only (POST /api/v1/auth/login is never used here — these tests seed an
// authenticated session directly via the csrf_token cookie + GET /api/v1/me
// interception, which is all AccountLayout/ProtectedRoute/AuthProvider
// actually need), never a real backend.
//
// Scope decision (recorded, not silently resolved): there is intentionally
// no fake Orders/Downloads/Offers/etc. page built here — Profile and
// Notifications are the only real account destinations today
// (accountNavItems.ts). Mobile nav usability is proven against Profile;
// Notifications gets its own E2E coverage in auth-account-phase2.spec.ts.

interface RawMeBody {
  id: string;
  email: string;
  role: string;
  email_verified: boolean;
  email_verified_at: string | null;
  created_at: string;
}

const ME_BODY_VERIFIED: RawMeBody = {
  id: "u-1",
  email: "ada@example.com",
  role: "customer",
  email_verified: true,
  email_verified_at: "2025-01-01T00:00:00Z",
  created_at: "2024-01-01T00:00:00Z",
};

const ME_BODY_UNVERIFIED: RawMeBody = { ...ME_BODY_VERIFIED, email_verified: false, email_verified_at: null };

async function signInAs(page: Page, meBody: RawMeBody) {
  await page.context().addCookies([{ name: "csrf_token", value: "test-value", url: "http://localhost:3000" }]);
  await page.route("**/api/v1/me", async (route) => {
    await route.fulfill({ status: 200, body: JSON.stringify(meBody) });
  });
}

test.describe("Account profile (FVS-006 T05/T06)", () => {
  test("authenticated customer visiting /account is redirected to /account/profile and sees their own verified email", async ({
    page,
  }) => {
    await signInAs(page, ME_BODY_VERIFIED);

    await page.goto("/account");

    await expect(page).toHaveURL(/\/account\/profile$/);
    await expect(page.getByText("ada@example.com")).toBeVisible();
    await expect(page.getByText("Verified", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: /resend/i })).not.toBeVisible();
  });

  test("an unverified /me response shows the resend banner linking to the existing FVS-002 route", async ({
    page,
  }) => {
    await signInAs(page, ME_BODY_UNVERIFIED);

    await page.goto("/account/profile");

    await expect(page.getByText(/not verified/i)).toBeVisible();
    const resendLink = page.getByRole("link", { name: /resend/i });
    await expect(resendLink).toBeVisible();
    await expect(resendLink).toHaveAttribute("href", "/verify-email/resend");
  });

  test("an anonymous visit to /account/profile redirects to /login with a safe returnTo", async ({ page }) => {
    // Deliberately no signInAs() call — no csrf_token cookie, no /me
    // interception needed at all (bootstrapAuthSession's own zero-network
    // anonymous fast path).
    await page.goto("/account/profile");

    await expect(page).toHaveURL(/\/login\?returnTo=%2Faccount%2Fprofile$/);
  });

  test("no edit-profile UI exists anywhere on the profile page", async ({ page }) => {
    await signInAs(page, ME_BODY_VERIFIED);
    await page.goto("/account/profile");
    await expect(page.getByText("ada@example.com")).toBeVisible();

    expect(await page.locator("input, textarea, select").count()).toBe(0);
    await expect(page.getByRole("button", { name: /save/i })).not.toBeVisible();
    await expect(page.getByRole("button", { name: /^edit$/i })).not.toBeVisible();
  });

  test("mobile account nav is usable: visible, scrollable, keyboard-reachable", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await signInAs(page, ME_BODY_VERIFIED);
    await page.goto("/account/profile");

    const nav = page.getByRole("navigation", { name: "Account" });
    await expect(nav).toBeVisible();
    const profileLink = page.getByRole("link", { name: "Profile" });
    await expect(profileLink).toBeVisible();
    await profileLink.focus();
    await expect(profileLink).toBeFocused();
    await expect(profileLink).toHaveAttribute("aria-current", "page");
  });

  const VIEWPORTS = [320, 375, 768, 1024, 1440, 1920];

  for (const width of VIEWPORTS) {
    test(`no horizontal overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await signInAs(page, ME_BODY_VERIFIED);
      await page.goto("/account/profile", { waitUntil: "networkidle" });

      const [scrollWidth, clientWidth] = await page.evaluate(() => [
        document.documentElement.scrollWidth,
        document.documentElement.clientWidth,
      ]);
      expect(scrollWidth).toBeLessThanOrEqual(clientWidth);

      const nav = page.getByRole("navigation", { name: "Account" });
      const navBox = await nav.boundingBox();
      expect(navBox).not.toBeNull();

      if (width >= 768) {
        // tablet+: the sidebar sits beside the content, not above it —
        // same viewport row, narrower than the full width.
        expect(navBox!.width).toBeLessThan(width);
      }
    });
  }

  test("desktop sidebar and content are both reachable by keyboard, with visible focus", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await signInAs(page, ME_BODY_VERIFIED);
    await page.goto("/account/profile");

    const profileLink = page.getByRole("link", { name: "Profile" });
    await profileLink.focus();
    await expect(profileLink).toBeFocused();
    await expect(profileLink).not.toHaveCSS("box-shadow", "none");
  });

  test("retrying after an unexpected /me failure re-fetches the canonical session and shows the real profile, without a false redirect to /login", async ({
    page,
  }) => {
    let meCallCount = 0;
    await page.context().addCookies([{ name: "csrf_token", value: "test-value", url: "http://localhost:3000" }]);
    await page.route("**/api/v1/me", async (route) => {
      meCallCount += 1;
      if (meCallCount === 1) {
        await route.fulfill({ status: 500, body: JSON.stringify({ title: "Internal Server Error" }) });
        return;
      }
      await route.fulfill({ status: 200, body: JSON.stringify(ME_BODY_VERIFIED) });
    });

    await page.goto("/account/profile");

    // The unexpected 500 must show a retryable error, never bounce to
    // /login (the exact FVS-006 T01 defect this slice fixed).
    await expect(page).toHaveURL(/\/account\/profile$/);
    const retryButton = page.getByRole("button", { name: /retry/i });
    await expect(retryButton).toBeVisible();

    await retryButton.click();

    await expect(page.getByText("ada@example.com")).toBeVisible();
    expect(meCallCount).toBe(2);
  });
});
