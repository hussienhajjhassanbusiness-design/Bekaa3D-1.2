import { test, expect, type Page } from "@playwright/test";
import { stubEmptyCart } from "./support/stubCart";
import { E2E_ORIGIN } from "./support/origin";

// Redesign Batch 9 — the dedicated admin shell and representative queues at
// the six QA widths: no storefront header/footer for an administrator, the
// 256px sidebar from 1024px and the drawer below it (keyboard, Escape, route
// change), one <main>, and no page-level horizontal overflow — wide tables
// scroll inside their own card. Route interception only; no backend.

const WIDTHS = [320, 375, 768, 1024, 1280, 1440];
const usd = (amount_cents: number) => ({ amount_cents, currency: "USD" });
const uuid = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const ADMIN_ME = {
  id: "admin-1",
  email: "operations.lead.with.a.long.address@bekaa3d-example.com",
  role: "admin",
  email_verified: true,
  email_verified_at: "2025-01-01T00:00:00Z",
  created_at: "2024-01-01T00:00:00Z",
};
const CUSTOMER_ME = { ...ADMIN_ME, id: "c-1", email: "customer@example.com", role: "customer" };

function orderSummary(n: number) {
  return {
    id: uuid(n),
    order_number: `B3D-LONG${String(n).padStart(4, "0")}`,
    customer_id: "c-1",
    customer_email: `a.very.long.customer.email.address.number.${n}@example-customer-domain.com`,
    status: "in_progress",
    fulfillment_method: "delivery",
    payment_method: "cash",
    payment_due: true,
    amount_due: usd(1234567),
    total: usd(1234567),
    estimated_dispatch_at: null,
    placed_at: "2026-11-11T10:00:00Z",
  };
}

async function asAdmin(page: Page, me: Record<string, unknown> = ADMIN_ME) {
  await page.context().addCookies([{ name: "csrf_token", value: "e2e-csrf-value", url: E2E_ORIGIN }]);
  await stubEmptyCart(page);
  await page.route(/\/api\/v1\/me$/, (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(me) })
  );
  await page.route(/\/api\/v1\/admin\/orders(\?.*)?$/, (r) =>
    r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [orderSummary(1), orderSummary(2), orderSummary(3)], next_cursor: "next" }),
    })
  );
  await page.route(/\/api\/v1\/admin\/contact-messages(\?.*)?$/, (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], next_cursor: null }) })
  );
}

async function expectNoOverflow(page: Page, label: string) {
  const [scrollWidth, clientWidth] = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    document.documentElement.clientWidth,
  ]);
  expect(scrollWidth, `${label}: horizontal page overflow`).toBeLessThanOrEqual(clientWidth);
}

test("an administrator gets the admin shell, never the storefront chrome, at every width", async ({ page }) => {
  await asAdmin(page);
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/admin/orders");
    await expect(page.getByRole("heading", { level: 1, name: "Orders" })).toBeVisible();
    await expect(page.getByRole("main")).toHaveCount(1);
    await expect(page.getByRole("contentinfo")).toHaveCount(0);
    await expect(page.getByRole("navigation", { name: "Main" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Chat with us on WhatsApp" })).toHaveCount(0);

    const sidebarNav = page.getByRole("navigation", { name: "Admin" });
    const menuButton = page.getByRole("button", { name: "Open admin menu" });
    if (width >= 1024) {
      await expect(sidebarNav).toBeVisible();
      expect((await page.getByRole("complementary", { name: "Admin sidebar" }).boundingBox())!.width).toBe(256);
      await expect(menuButton).toBeHidden();
      await expect(sidebarNav.getByRole("link", { name: "Orders" })).toHaveAttribute("aria-current", "page");
    } else {
      await expect(sidebarNav).toBeHidden();
      await expect(menuButton).toBeVisible();
    }

    // Wide tables scroll inside their own card; the page never does.
    await expect(page.getByText("B3D-LONG0001")).toBeVisible();
    await expectNoOverflow(page, `${width}px orders`);
    const next = (await page.getByRole("button", { name: "Next" }).boundingBox())!;
    expect(next.height, `${width}px: pager target`).toBeGreaterThanOrEqual(44);
    expect(next.x + next.width, `${width}px: pager clipped`).toBeLessThanOrEqual(width);
  }
});

test("mobile drawer: keyboard open, focus inside, Escape returns focus, a nav link closes it", async ({ page }) => {
  await asAdmin(page);
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/admin/orders");
  const menuButton = page.getByRole("button", { name: "Open admin menu" });
  await menuButton.focus();
  await page.keyboard.press("Enter");
  const drawer = page.getByRole("dialog", { name: "Admin menu" });
  await expect(drawer).toBeVisible();
  await expect(page.getByRole("button", { name: "Close admin menu" })).toBeFocused();
  await expect(drawer.getByRole("link", { name: "Orders" })).toHaveAttribute("aria-current", "page");
  const box = (await drawer.boundingBox())!;
  expect(box.x + box.width).toBeLessThanOrEqual(375);
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  await expect(menuButton).toBeFocused();

  await menuButton.click();
  await drawer.getByRole("link", { name: "Contact messages" }).click();
  await expect(page).toHaveURL(/\/admin\/contact-messages$/);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1, name: "Contact messages" })).toBeVisible();
  await expectNoOverflow(page, "375px contact queue");
});

test("the skip link lands on the admin content, past the sidebar", async ({ page }) => {
  await asAdmin(page);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/admin/orders");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
  await expect(page.locator("#main-content")).not.toContainText("Catalogue");
});

test("a customer on an admin URL keeps the storefront chrome and sees only the 404", async ({ page }) => {
  await asAdmin(page, CUSTOMER_ME);
  await page.goto("/admin/orders");
  await expect(page.getByText(/page not found/i)).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main" }).first()).toBeAttached();
  await expect(page.getByRole("navigation", { name: "Admin" })).toHaveCount(0);
  await expect(page.getByRole("contentinfo")).toHaveCount(1);
});
