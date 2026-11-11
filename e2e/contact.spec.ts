import { test, expect, type Page, type Route } from "@playwright/test";
import { E2E_CAPTCHA_TOKEN, routeFakeTurnstile, waitForCaptchaToken } from "./support/fakeTurnstile";
import { stubEmptyCart } from "./support/stubCart";

// Phase 6B-1 — Contact against a deterministic stand-in for backend 2dfb27b
// (engagement/api/contact_messages.py): public POST /api/v1/contact-messages
// and the admin queue /api/v1/admin/contact-messages[/{id}]. Route
// interception only: no backend on :8000, no media server on :8001.

type Json = Record<string, unknown>;
const uuid = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const ADMIN_ME = { id: "admin-1", email: "admin@example.com", role: "admin", email_verified: true, email_verified_at: "2025-01-01T00:00:00Z", created_at: "2024-01-01T00:00:00Z" };
const CUSTOMER_ME = { ...ADMIN_ME, id: "customer-1", email: "customer@example.com", role: "customer" };

function problem(status: number, code: string, extra: Json = {}, headers: Record<string, string> = {}) {
  return {
    status,
    headers,
    contentType: "application/problem+json",
    body: JSON.stringify({ type: "about:blank", title: "RAW TITLE", status, detail: "RAW DETAIL", code, errors: [], ...extra }),
  };
}

async function asGuest(page: Page) {
  await page.route(/\/api\/v1\/me$/, (r) => r.fulfill(problem(401, "AUTH_REQUIRED")));
  await page.route(/\/api\/v1\/auth\/refresh$/, (r) => r.fulfill(problem(401, "AUTH_REQUIRED")));
}

async function asUser(page: Page, me: Json) {
  await page.context().addCookies([{ name: "csrf_token", value: "e2e-csrf-value", url: "http://localhost:3000" }]);
  await stubEmptyCart(page);
  await page.route(/\/api\/v1\/me$/, (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(me) }));
}

async function fillContact(page: Page) {
  await page.getByLabel("Name").fill("Rana Haddad");
  await page.getByLabel("Email").fill("rana@example.com");
  await page.getByLabel("Phone (optional)").fill("+961 70 123 456");
  await page.getByLabel("Subject (optional)").fill("PETG prints");
  await page.getByLabel("Message").fill("Do you print in PETG?\nThanks!");
}

test.describe("Contact (Phase 6B-1)", () => {
  test("validates client-side, refuses a used captcha, retries with a fresh token and succeeds", async ({ page }) => {
    await asGuest(page);
    await routeFakeTurnstile(page);
    const bodies: Json[] = [];
    await page.route(/\/api\/v1\/contact-messages$/, (route: Route) => {
      const body = route.request().postDataJSON() as Json;
      bodies.push(body);
      if (bodies.length === 1) return route.fulfill(problem(400, "CAPTCHA_INVALID"));
      return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: uuid(1), created_at: "2026-11-11T10:00:00Z" }) });
    });

    await page.goto("/contact");
    await expect(page.getByRole("heading", { name: "Contact us" })).toBeVisible();
    await waitForCaptchaToken(page);
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.getByText("Enter your name.").first()).toBeVisible();
    expect(bodies).toHaveLength(0);

    await fillContact(page);
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText("The verification check expired or failed");
    await expect(page.getByText("RAW DETAIL")).toHaveCount(0);

    await waitForCaptchaToken(page);
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.getByText("your message has been sent")).toBeVisible();
    await expect(page.getByText(uuid(1))).toHaveCount(0);
    expect(bodies[1]).toEqual({
      name: "Rana Haddad",
      email: "rana@example.com",
      phone: "+961 70 123 456",
      subject: "PETG prints",
      message: "Do you print in PETG?\nThanks!",
      captcha_token: E2E_CAPTCHA_TOKEN,
    });
  });

  test("server validation and rate limit show frontend copy only", async ({ page }) => {
    await asGuest(page);
    await routeFakeTurnstile(page);
    let calls = 0;
    await page.route(/\/api\/v1\/contact-messages$/, (route) => {
      calls += 1;
      if (calls === 1) return route.fulfill(problem(422, "VALIDATION_ERROR", { errors: [{ loc: ["body", "email"], msg: "RAW MSG", type: "value_error" }] }));
      return route.fulfill(problem(429, "RATE_LIMITED", {}, { "Retry-After": "3600" }));
    });
    await page.goto("/contact");
    await waitForCaptchaToken(page);
    await fillContact(page);
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText("Please check: Email.");
    await waitForCaptchaToken(page);
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText("Please try again in about 60 minutes.");
    await expect(page.getByText(/RAW/)).toHaveCount(0);
  });

  test("keyboard-only submission on a phone-sized viewport", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await asGuest(page);
    await routeFakeTurnstile(page);
    await page.route(/\/api\/v1\/contact-messages$/, (route) =>
      route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: uuid(2), created_at: "2026-11-11T10:00:00Z" }) })
    );
    await page.goto("/contact");
    await waitForCaptchaToken(page);
    await page.getByLabel("Name").focus();
    await page.keyboard.type("Karim");
    await page.keyboard.press("Tab");
    await page.keyboard.type("karim@example.com");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    await page.keyboard.type("Hello there");
    await expect(page.getByLabel("Message")).toHaveValue("Hello there");
    await page.getByRole("button", { name: "Send message" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByText("your message has been sent")).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    expect(overflow).toBe(false);
  });

  test("admin queue -> detail -> confirmed status move with CSRF", async ({ page }) => {
    await asUser(page, ADMIN_ME);
    const msg: Json = {
      id: uuid(10), name: "Rana Haddad", email: "rana@example.com", phone: null, subject: "PETG prints",
      message: "<script>alert(1)</script>\nThanks", status: "new", created_at: "2026-11-10T10:00:00Z", updated_at: "2026-11-10T10:00:00Z", user_id: null, order_id: null,
    };
    const listUrls: string[] = [];
    const patches: { body: unknown; csrf: string | null }[] = [];
    await page.route(/\/api\/v1\/admin\/contact-messages(\?.*)?$/, (route) => {
      listUrls.push(route.request().url());
      const status = new URL(route.request().url()).searchParams.get("status");
      const items = status && status !== msg.status ? [] : [msg];
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items, next_cursor: null }) });
    });
    await page.route(/\/api\/v1\/admin\/contact-messages\/[^/?]+$/, (route) => {
      if (route.request().method() === "PATCH") {
        patches.push({ body: route.request().postDataJSON(), csrf: route.request().headers()["x-csrf-token"] ?? null });
        Object.assign(msg, (route.request().postDataJSON() as Json));
      }
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(msg) });
    });

    await page.goto("/admin/contact-messages");
    await expect(page.getByRole("navigation", { name: "Admin" }).getByRole("link", { name: "Contact messages" })).toHaveAttribute("aria-current", "page");
    await page.getByLabel("Status").selectOption("new");
    await expect.poll(() => listUrls.at(-1)).toContain("status=new");
    await page.getByRole("link", { name: "Rana Haddad" }).click();
    await expect(page.getByRole("heading", { name: "PETG prints" })).toBeVisible();
    await expect(page.getByText("<script>alert(1)</script>")).toBeVisible();
    await page.getByRole("button", { name: "Mark replied" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "Mark replied" }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByText("Replied", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Mark read" })).toHaveCount(0);
    expect(patches).toEqual([{ body: { status: "replied" }, csrf: "e2e-csrf-value" }]);
  });

  test("a signed-in customer gets the normal 404 on the admin queue", async ({ page }) => {
    await asUser(page, CUSTOMER_ME);
    let adminCalls = 0;
    await page.route(/\/api\/v1\/admin\//, (route) => {
      adminCalls += 1;
      return route.fulfill(problem(404, "NOT_FOUND"));
    });
    await page.goto("/admin/contact-messages");
    await expect(page.getByText(/page not found/i)).toBeVisible();
    await expect(page.getByText("Contact messages")).toHaveCount(0);
    expect(adminCalls).toBe(0);
  });
});
