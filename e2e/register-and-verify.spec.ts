import { test, expect } from "@playwright/test";

// FVS002-T12 — one deterministic, backend-independent E2E spec proving the
// full register -> check-email -> (simulated email link) -> verify ->
// /login-prompt flow, added to the existing "smoke" project (see
// playwright.config.ts). Uses Playwright route interception for the two
// endpoints this flow actually calls — never a real backend, never a
// second local server, never a test-only hook added to production code.

const VALID_TOKEN = "a".repeat(43);

test.describe("Register-to-verify flow (FVS002-T12)", () => {
  test("register -> check-email success -> follow email link -> verify success -> /login reachable", async ({
    page,
  }) => {
    let registerRequestBody: unknown;
    await page.route("**/api/v1/auth/register", async (route) => {
      registerRequestBody = route.request().postDataJSON();
      await route.fulfill({ status: 202, body: JSON.stringify({ message: "check your email" }) });
    });

    let verifyRequestBody: unknown;
    let verifyRequestUrl = "";
    await page.route("**/api/v1/auth/verify-email", async (route) => {
      verifyRequestUrl = route.request().url();
      verifyRequestBody = route.request().postDataJSON();
      await route.fulfill({ status: 204, body: "" });
    });

    // 1-3: visit /register, fill valid email/password, submit.
    await page.goto("/register");
    await page.getByLabel(/email/i).fill("ada@example.com");
    await page.getByLabel(/password/i).fill("correct-horse-battery");
    await page.getByRole("button", { name: /create account/i }).click();

    // 4-5: intercepted register returns 202; UI shows the enumeration-safe
    // check-email success state.
    await expect(page.getByText(/check your email/i)).toBeVisible();
    expect(registerRequestBody).toEqual({ email: "ada@example.com", password: "correct-horse-battery" });

    // 6: simulate following a real-format frontend email link — a fresh
    // navigation to /verify-email#token=<43-char-test-token>.
    await page.goto(`/verify-email#token=${VALID_TOKEN}`);

    // 7-8: verify endpoint interception observes exactly one POST with the
    // confirmed path/body, no trailing slash, returning 204.
    await expect(page.getByText(/verified/i)).toBeVisible();
    expect(verifyRequestUrl).toContain("/api/v1/auth/verify-email");
    expect(verifyRequestUrl.endsWith("/")).toBe(false);
    expect(verifyRequestBody).toEqual({ token: VALID_TOKEN });

    // 9-10: verification success UI appears, with a reachable /login prompt.
    const loginLink = page.getByRole("link", { name: /log in/i });
    await expect(loginLink).toBeVisible();
    await expect(loginLink).toHaveAttribute("href", "/login");

    // FVS-002 BATCH 4 Part F fix: the token no longer lingers in the
    // visible URL fragment after capture.
    expect(page.url()).not.toContain("token=");
  });
});

test.describe("Resend flow smoke (FVS002-T12 optional)", () => {
  test("resend -> valid email -> enumeration-safe success -> cooldown visible and button disabled", async ({
    page,
  }) => {
    await page.route("**/api/v1/auth/resend-verification", (route) =>
      route.fulfill({ status: 202, body: JSON.stringify({ message: "sent" }) })
    );

    await page.goto("/verify-email/resend");
    await page.getByLabel(/email/i).fill("ada@example.com");
    await page.getByRole("button", { name: /resend/i }).click();

    await expect(page.getByText(/if an account exists/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /resend/i })).toBeDisabled();
  });
});
