import { test, expect, type Page } from "@playwright/test";
import { stubGuest } from "./support/stubGuest";
import { stubEmptyCart } from "./support/stubCart";

// Redesign Batch 2 — the shared storefront chrome (Header with the Login /
// Account entry and the mobile menu, Footer) at every supported width.
// Route interception only; never a real backend.

const ME_BODY = {
  id: "u-1",
  email: "ada@example.com",
  role: "customer",
  email_verified: true,
  email_verified_at: "2025-01-01T00:00:00Z",
  created_at: "2024-01-01T00:00:00Z",
};

async function signIn(page: Page) {
  await stubEmptyCart(page);
  await page.context().addCookies([{ name: "csrf_token", value: "test-value", url: "http://localhost:3000" }]);
  await page.route(/\/api\/v1\/me$/, (route) => route.fulfill({ status: 200, body: JSON.stringify(ME_BODY) }));
}

async function expectNoHorizontalOverflow(page: Page) {
  const [scrollWidth, clientWidth] = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    document.documentElement.clientWidth,
  ]);
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
}

const banner = (page: Page) => page.getByRole("banner");

test.describe("Storefront chrome (redesign batch 2)", () => {
  for (const width of [320, 375, 768, 1024, 1280, 1440]) {
    test(`signed out at ${width}px: 64px header, a reachable Sign in, the right navigation pattern, no overflow`, async ({
      page,
    }) => {
      await stubGuest(page);
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/contact");

      const header = await banner(page).boundingBox();
      expect(header?.height).toBe(64);

      const signIn = banner(page).getByRole("link", { name: "Sign in" });
      await expect(signIn).toBeVisible();
      await expect(signIn).toHaveAttribute("href", "/login?returnTo=%2Fcontact");
      await expect(banner(page).getByRole("link", { name: "Cart" })).toBeVisible();

      const desktopNav = banner(page).getByRole("navigation", { name: "Main" });
      const menuButton = banner(page).getByRole("button", { name: "Open menu" });
      if (width >= 1024) {
        await expect(desktopNav).toBeVisible();
        await expect(menuButton).toBeHidden();
      } else {
        await expect(desktopNav).toBeHidden();
        await expect(menuButton).toBeVisible();
        // Touch targets in the bar stay at least 40px.
        for (const control of [signIn, menuButton, banner(page).getByRole("link", { name: "Cart" })]) {
          const box = await control.boundingBox();
          expect(box!.width).toBeGreaterThanOrEqual(40);
          expect(box!.height).toBeGreaterThanOrEqual(40);
        }
      }

      await expect(page.getByRole("navigation", { name: "Footer" })).toBeVisible();
      await expectNoHorizontalOverflow(page);
    });
  }

  test("signed in: the header offers Account (to /account) at mobile and desktop widths", async ({ page }) => {
    await signIn(page);
    for (const width of [320, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/shop");
      const account = banner(page).getByRole("link", { name: "Account" });
      await expect(account).toBeVisible();
      await expect(account).toHaveAttribute("href", "/account");
      await expect(banner(page).getByRole("link", { name: "Sign in" })).toHaveCount(0);
    }
  });

  test("the header stays in view while the page scrolls", async ({ page }) => {
    await stubGuest(page);
    await page.setViewportSize({ width: 1280, height: 600 });
    await page.goto("/about");
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);

    const header = await banner(page).boundingBox();
    expect(header?.y).toBe(0);
  });

  test("mobile menu: keyboard open, focus inside, Escape closes and returns focus, no overflow", async ({ page }) => {
    await stubGuest(page);
    await page.setViewportSize({ width: 375, height: 800 });
    await page.goto("/");

    const toggle = banner(page).getByRole("button", { name: "Open menu" });
    await toggle.focus();
    await expect(toggle).not.toHaveCSS("box-shadow", "none");
    await page.keyboard.press("Enter");

    const sheet = page.getByRole("dialog", { name: "Menu" });
    await expect(sheet).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(sheet.getByRole("button", { name: "Close menu" })).toBeFocused();
    await expect(sheet.getByRole("navigation", { name: "Main" }).getByRole("link")).toHaveCount(5);
    await expect(sheet.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login?returnTo=%2F");

    // The sheet fits the viewport and the page behind it does not scroll.
    const box = await sheet.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(375);
    await expect(page.locator("html")).toHaveCSS("overflow", "hidden");
    await expectNoHorizontalOverflow(page);

    await page.keyboard.press("Escape");
    await expect(sheet).toBeHidden();
    await expect(toggle).toBeFocused();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  test("mobile menu: following a link navigates and closes the sheet", async ({ page }) => {
    await stubGuest(page);
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto("/");

    await banner(page).getByRole("button", { name: "Open menu" }).click();
    const sheet = page.getByRole("dialog", { name: "Menu" });
    await sheet.getByRole("link", { name: "Contact" }).click();

    await expect(page).toHaveURL(/\/contact$/);
    await expect(sheet).toBeHidden();
    await expect(banner(page).getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login?returnTo=%2Fcontact");
  });

  test("footer: only real public destinations, nothing from the admin area", async ({ page }) => {
    await stubGuest(page);
    await page.goto("/");

    const hrefs = await page
      .getByRole("navigation", { name: "Footer" })
      .getByRole("link")
      .evaluateAll((links) => links.map((link) => link.getAttribute("href")));
    expect(hrefs).toEqual(["/shop", "/bring-your-idea", "/about", "/contact", "/account", "/account/wishlist", "/cart"]);
  });
});
