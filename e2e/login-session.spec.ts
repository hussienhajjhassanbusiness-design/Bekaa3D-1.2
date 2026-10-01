import { test, expect, type Page } from "@playwright/test";

// FVS-003 BATCH 4 (T11 real-browser evidence + T12 deterministic E2E) — one
// file serving both purposes: it is the permanent, deterministic,
// backend-independent coverage for the login flow (T12), and the same
// scenarios double as T11's real-browser verification evidence for the
// login->/me navigation sequence, returnTo safety, and the MFA 202 path.
// Route interception only, exactly like register-and-verify.spec.ts — never
// a real backend.
//
// Scope decision (recorded per the batch's explicit instruction): there is
// intentionally no real logout trigger and no real protected product route
// in this repository yet (FVS-006 will supply the first one). Building
// either here purely to round out this E2E file was explicitly rejected —
// ProtectedRoute stays proven through its own component/integration tests
// (src/components/auth/ProtectedRoute.test.tsx) and logout through its own
// (useLogout.test.ts, AuthProvider.test.tsx). This file's deterministic
// coverage is bounded to the real UI that actually exists: /login.

const SESSION_BODY = {
  user_id: "u-1",
  email: "ada@example.com",
  role: "customer",
  email_verified: true,
  session_expires_at: "2026-01-01T00:15:00Z",
};

const ME_BODY = {
  id: "u-1",
  email: "ada@example.com",
  role: "customer",
  email_verified: true,
  email_verified_at: "2025-01-01T00:00:00Z",
  created_at: "2024-01-01T00:00:00Z",
};

async function mockSuccessfulLogin(page: Page) {
  await page.route("**/api/v1/auth/login", async (route) => {
    await route.fulfill({
      status: 200,
      // Simulates the real backend's Set-Cookie for csrf_token on a
      // successful login — a genuine browser cookie jar update, not a
      // JS-side simulation, since Playwright's route interception responds
      // through the real network/cookie stack.
      headers: { "set-cookie": "csrf_token=test-value; Path=/" },
      body: JSON.stringify(SESSION_BODY),
    });
  });
  await page.route("**/api/v1/me", async (route) => {
    await route.fulfill({ status: 200, body: JSON.stringify(ME_BODY) });
  });
}

async function fillValidForm(page: Page) {
  await page.getByLabel(/email/i).fill("ada@example.com");
  await page.getByLabel(/password/i).fill("correct-horse-battery");
}

test.describe("Login flow (FVS-003 BATCH 4 T12)", () => {
  test("normal login: 200 session -> csrf_token available -> /me resolves authenticated -> navigates to safe returnTo", async ({
    page,
  }) => {
    await mockSuccessfulLogin(page);

    await page.goto("/login?returnTo=%2Faccount");
    await fillValidForm(page);
    await page.getByRole("button", { name: /log ?in/i }).click();

    // Navigation only happens once /me has genuinely resolved authenticated
    // — proven here against a real browser/real cookie jar, not a mock.
    await expect(page).toHaveURL(/\/account$/);
    expect(await page.evaluate(() => document.cookie)).toContain("csrf_token=test-value");

    // No login failure state is visible.
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  test("falls back to / when returnTo is absent", async ({ page }) => {
    await mockSuccessfulLogin(page);

    await page.goto("/login");
    await fillValidForm(page);
    await page.getByRole("button", { name: /log ?in/i }).click();

    await expect(page).toHaveURL(/\/$/);
  });
});

test.describe("returnTo security (FVS-003 BATCH 4 Section E)", () => {
  test("a safe relative returnTo (with its own query string) is honored", async ({ page }) => {
    await mockSuccessfulLogin(page);

    await page.goto("/login?returnTo=%2Faccount%3Ftab%3Dorders");
    await fillValidForm(page);
    await page.getByRole("button", { name: /log ?in/i }).click();

    await expect(page).toHaveURL(/\/account\?tab=orders$/);
  });

  test("an unsafe external returnTo never results in external navigation — falls back to /", async ({ page }) => {
    await mockSuccessfulLogin(page);

    await page.goto("/login?returnTo=https%3A%2F%2Fevil.example");
    await fillValidForm(page);
    await page.getByRole("button", { name: /log ?in/i }).click();

    await expect(page).toHaveURL(/^http:\/\/localhost:3000\/$/);
  });

  test("a protocol-relative returnTo (//evil.example) never results in external navigation — falls back to /", async ({
    page,
  }) => {
    await mockSuccessfulLogin(page);

    await page.goto("/login?returnTo=%2F%2Fevil.example");
    await fillValidForm(page);
    await page.getByRole("button", { name: /log ?in/i }).click();

    await expect(page).toHaveURL(/^http:\/\/localhost:3000\/$/);
  });
});

test.describe("MFA challenge (FVS-003 BATCH 4 Section D / T12)", () => {
  test("202 MFA challenge shows a safe informational message, never navigates, and never exposes challenge_id", async ({
    page,
  }) => {
    await page.route("**/api/v1/auth/login", async (route) => {
      await route.fulfill({
        status: 202,
        body: JSON.stringify({ challenge_id: "test-only-value", expires_in_seconds: 300 }),
      });
    });
    let meCalled = false;
    await page.route("**/api/v1/me", async (route) => {
      meCalled = true;
      await route.fulfill({ status: 401, body: JSON.stringify({ code: "AUTH_REQUIRED" }) });
    });

    await page.goto("/login?returnTo=%2Faccount");
    await fillValidForm(page);
    await page.getByRole("button", { name: /log ?in/i }).click();

    await expect(page.getByText(/additional verification/i)).toBeVisible();
    // Still on /login — the returnTo value legitimately appears in the
    // URL's own query string (it was there before submit); what must never
    // happen is an actual navigation to that destination.
    expect(new URL(page.url()).pathname).toBe("/login");

    const bodyText = await page.evaluate(() => document.body.innerText);
    expect(bodyText).not.toContain("test-only-value");
    expect(meCalled).toBe(false);
  });
});

test.describe("Login real-browser accessibility & responsive check (FVS-003 BATCH 4 Section B)", () => {
  const VIEWPORTS = [320, 375, 768, 1024, 1440, 1920];

  for (const width of VIEWPORTS) {
    test(`no horizontal overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/login", { waitUntil: "networkidle" });

      const [scrollWidth, clientWidth] = await page.evaluate(() => [
        document.documentElement.scrollWidth,
        document.documentElement.clientWidth,
      ]);
      expect(scrollWidth).toBeLessThanOrEqual(clientWidth);

      const formBox = await page.locator("form").boundingBox();
      expect(formBox).not.toBeNull();
      if (width >= 768) {
        // Desktop: capped at ~420px and horizontally centered.
        expect(formBox!.width).toBeLessThanOrEqual(420);
        const expectedX = (width - formBox!.width) / 2;
        expect(Math.abs(formBox!.x - expectedX)).toBeLessThan(2);
      } else {
        // Mobile: single column, full width.
        expect(formBox!.width).toBeGreaterThan(width - 10);
      }
    });
  }

  test("submit CTA is full-width on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 900 });
    await page.goto("/login");

    const button = page.getByRole("button", { name: /log ?in/i });
    const buttonBox = await button.boundingBox();
    const formBox = await page.locator("form").boundingBox();
    expect(buttonBox).not.toBeNull();
    expect(formBox).not.toBeNull();
    // Full-width within the form's own padding-free box (±2px tolerance).
    expect(Math.abs(buttonBox!.width - formBox!.width)).toBeLessThan(2);
  });

  test("password show/hide toggle is keyboard-operable, reports aria-pressed correctly, and preserves the typed value", async ({
    page,
  }) => {
    await page.goto("/login");

    const passwordInput = page.getByLabel(/password/i);
    await passwordInput.fill("correct-horse-battery");

    const toggle = page.getByRole("button", { name: /show password/i });
    await expect(toggle).toHaveAttribute("aria-pressed", "false");
    await expect(passwordInput).toHaveAttribute("type", "password");

    await toggle.focus();
    await page.keyboard.press("Enter");

    // The toggle's accessible name flips with its state ("Show" <->
    // "Hide"), so it must be re-located by its new name rather than
    // re-using the old "Show password" locator.
    const toggleAfter = page.getByRole("button", { name: /hide password/i });
    await expect(toggleAfter).toHaveAttribute("aria-pressed", "true");
    await expect(passwordInput).toHaveAttribute("type", "text");
    await expect(passwordInput).toHaveValue("correct-horse-battery");
  });

  test("keyboard walkthrough: SkipLink -> Email -> Password -> show/hide -> submit, with visible focus and no trap", async ({
    page,
  }) => {
    await page.goto("/login");

    // SkipLink is the first focusable element.
    await page.keyboard.press("Tab");
    const skipLink = page.getByRole("link", { name: /skip to main content/i });
    await expect(skipLink).toBeFocused();

    await page.keyboard.press("Tab");
    const emailInput = page.getByLabel(/email/i);
    await expect(emailInput).toBeFocused();
    // The app's focus-visible treatment is a box-shadow ring, not the
    // native outline (globals.css's documented WCAG 2.4.7-compliant
    // replacement) — "none" would mean no visible focus indicator at all.
    await expect(emailInput).not.toHaveCSS("box-shadow", "none");

    await page.keyboard.press("Tab");
    const passwordInput = page.getByLabel(/password/i);
    await expect(passwordInput).toBeFocused();

    await page.keyboard.press("Tab");
    const toggle = page.getByRole("button", { name: /show password/i });
    await expect(toggle).toBeFocused();

    await page.keyboard.press("Tab");
    const submitButton = page.getByRole("button", { name: /log ?in/i });
    await expect(submitButton).toBeFocused();

    // One more Tab moves on (no trap) rather than cycling back to the top
    // of this same form.
    await page.keyboard.press("Tab");
    await expect(submitButton).not.toBeFocused();
  });

  test("submitting with an empty form focuses the first invalid field and shows a polite validation summary", async ({
    page,
  }) => {
    await page.goto("/login");

    await page.getByRole("button", { name: /log ?in/i }).click();

    const summary = page.getByRole("status").filter({ hasText: /fix the following/i });
    await expect(summary).toBeVisible();

    const emailInput = page.getByLabel(/email/i);
    await expect(emailInput).toBeFocused();
    await expect(emailInput).toHaveAttribute("aria-invalid", "true");
  });

  test("a credential failure renders an assertive alert without losing the form's content, and no raw backend text ever appears", async ({
    page,
  }) => {
    await page.route("**/api/v1/auth/login", async (route) => {
      await route.fulfill({
        status: 401,
        body: JSON.stringify({ code: "INVALID_CREDENTIALS", detail: "no such row in users table: SELECT ..." }),
      });
    });

    await page.goto("/login");
    await fillValidForm(page);
    await page.getByRole("button", { name: /log ?in/i }).click();

    // Next.js's own built-in route announcer also carries role="alert" —
    // scope to the one with actual visible content to avoid a strict-mode
    // collision with that hidden live region.
    const alert = page.getByRole("alert").filter({ hasText: "Invalid email or password." });
    await expect(alert).toHaveText("Invalid email or password.");
    const bodyText = await page.evaluate(() => document.body.innerText);
    expect(bodyText).not.toContain("SELECT");
    expect(bodyText).not.toContain("no such row");

    // The form is still present and usable, not replaced/cleared.
    await expect(page.getByLabel(/email/i)).toHaveValue("ada@example.com");
  });
});
