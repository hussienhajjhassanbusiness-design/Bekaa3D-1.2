import { test, expect, type Page } from "@playwright/test";
import { stubEmptyCart } from "./support/stubCart";
import { E2E_ORIGIN } from "./support/origin";

// Redesign Batch 5 — the account shell, Profile, Addresses and
// Notifications at the six QA widths, against mocked real-shaped data
// (route interception only; no backend). Asserts user-facing intent, not
// classes: one h1, no horizontal overflow, the "Account" navigation is
// discoverable at every width (every destination reachable and the
// current page marked), the nav sits beside the content from 1024px and
// above it below that, long Lebanese address strings and long
// notification text wrap, and the address dialog fits the viewport.

const WIDTHS = [320, 375, 768, 1024, 1280, 1440];
const NAV_LABELS = [
  "Profile",
  "Orders",
  "Offers",
  "Wishlist",
  "Addresses",
  "Notifications",
];
const NOW = "2026-11-10T10:00:00Z";

const ME = {
  id: "u-1",
  email: "ada.lovelace.long-address@example.com",
  role: "customer",
  email_verified: true,
  email_verified_at: "2025-01-01T00:00:00Z",
  created_at: "2024-03-01T00:00:00Z",
};

const HOME = {
  id: "addr-1",
  label: "Grandparents' house in the mountains above Jounieh",
  recipient_name: "Marie-Thérèse Abou Khalil El Haddad",
  phone: "+961 71 123 456",
  governorate: "keserwan_jbeil",
  city: "Jounieh",
  area: "Sahel Alma, near the Notre-Dame du Liban funicular",
  street: "Rue Mar Elias, Building Khoury-Sfeir, third floor",
  landmark_notes:
    "Blue gate next to the bakery, opposite the pharmacy; ring twice and call on arrival.",
  is_default: true,
  created_at: NOW,
  updated_at: NOW,
};
const ADDRESSES = [
  HOME,
  {
    id: "addr-2",
    label: "Work",
    recipient_name: "Ada",
    phone: "03 123 456",
    governorate: "baalbek_hermel",
    city: "Baalbek",
    area: null,
    street: null,
    landmark_notes: "Reception desk",
    is_default: false,
    created_at: NOW,
    updated_at: NOW,
  },
];

const CUSTOM_REQUEST_NOTIFICATION = {
  id: "n1",
  type: "custom_request",
  payload: {
    event:
      "custom_request.quoted_for_a_very_long_engineering_bracket_assembly_revision",
  },
  read: false,
  created_at: "2026-11-09T08:15:00Z",
};
const NOTIFICATIONS = [
  CUSTOM_REQUEST_NOTIFICATION,
  {
    id: "n2",
    type: "order",
    payload: {},
    read: true,
    created_at: "2026-11-08T17:40:00Z",
  },
];

async function signIn(page: Page) {
  await stubEmptyCart(page);
  await page
    .context()
    .addCookies([{ name: "csrf_token", value: "test-value", url: E2E_ORIGIN }]);
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({ status: 200, body: JSON.stringify(ME) }),
  );
  await page.route(/\/api\/v1\/me\/addresses$/, (route) =>
    route.fulfill({ status: 200, body: JSON.stringify({ items: ADDRESSES }) }),
  );
  await page.route(/\/api\/v1\/me\/notifications(\?.*)?$/, (route) =>
    route.fulfill({
      status: 200,
      body: JSON.stringify({ items: NOTIFICATIONS, next_cursor: null }),
    }),
  );
}

async function overflow(page: Page) {
  return page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
}

async function expectAccountNavDiscoverable(
  page: Page,
  width: number,
  current: string,
) {
  const nav = page.getByRole("navigation", { name: "Account" });
  await expect(nav).toBeVisible();
  for (const label of NAV_LABELS) {
    const link = nav.getByRole("link", { name: label });
    await link.scrollIntoViewIfNeeded();
    await expect(link).toBeVisible();
  }
  await expect(nav.getByRole("link", { name: current })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(nav.getByRole("button", { name: "Log out" })).toBeAttached();

  const navBox = (await nav.boundingBox())!;
  const contentBox = (await page
    .getByRole("region", { name: "Account content" })
    .boundingBox())!;
  if (width >= 1024) {
    // Side panel beside the content, never wider than the 256px sidebar.
    expect(navBox.x + navBox.width).toBeLessThanOrEqual(contentBox.x);
    expect(navBox.width).toBeLessThanOrEqual(256);
  } else {
    // Tab strip above full-width content (no squeezed two-column layout).
    expect(navBox.y + navBox.height).toBeLessThanOrEqual(contentBox.y);
    expect(contentBox.width).toBeGreaterThanOrEqual(width - 80);
  }
}

test.describe("Account pages responsive (redesign Batch 5)", () => {
  for (const width of WIDTHS) {
    test(`profile, addresses and notifications at ${width}px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 });
      await signIn(page);

      // Profile
      await page.goto("/account/profile");
      await expect(page.getByText(ME.email)).toBeVisible();
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
      await expect(
        page.getByRole("heading", { level: 1, name: "Profile" }),
      ).toBeVisible();
      await expect(page.getByText("Member since March 2024")).toBeVisible();
      expect(await overflow(page)).toBeLessThanOrEqual(0);
      await expectAccountNavDiscoverable(page, width, "Profile");

      // Addresses
      await page.goto("/account/addresses");
      const home = page.getByRole("article", { name: HOME.label });
      await expect(home).toBeVisible();
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
      await expect(home.getByText("Default", { exact: true })).toBeVisible();
      await expect(home.getByText("+961 71 123 456")).toBeVisible();
      await expect(
        home.getByText(
          /Rue Mar Elias, Building Khoury-Sfeir, third floor, Sahel Alma/,
        ),
      ).toBeVisible();
      await expect(home.getByText("Jounieh, Keserwan-Jbeil")).toBeVisible();
      expect(await overflow(page)).toBeLessThanOrEqual(0);
      await expectAccountNavDiscoverable(page, width, "Addresses");

      // Every action button stays inside its card and is a practical target.
      const homeBox = (await home.boundingBox())!;
      for (const name of [`Edit ${HOME.label}`, `Delete ${HOME.label}`]) {
        const box = (await page.getByRole("button", { name }).boundingBox())!;
        expect(box.height).toBeGreaterThanOrEqual(44);
        expect(box.x + box.width).toBeLessThanOrEqual(
          homeBox.x + homeBox.width + 0.5,
        );
      }

      await page.getByRole("button", { name: `Edit ${HOME.label}` }).click();
      const dialog = page.getByRole("dialog");
      await expect(dialog.getByLabel(/^label/i)).toBeFocused();
      const dialogBox = (await dialog.boundingBox())!;
      expect(dialogBox.width).toBeLessThanOrEqual(width);
      expect(dialogBox.x).toBeGreaterThanOrEqual(0);
      await expect(dialog.getByLabel(/governorate/i)).toHaveValue(
        "keserwan_jbeil",
      );
      expect(await overflow(page)).toBeLessThanOrEqual(0);
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);

      // Notifications
      await page.goto("/account/notifications");
      const first = page.getByRole("article", { name: "Custom request" });
      await expect(first).toBeVisible();
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
      await expect(first.getByText("Unread", { exact: true })).toBeVisible();
      await expect(first.locator("time")).toHaveAttribute(
        "datetime",
        CUSTOM_REQUEST_NOTIFICATION.created_at,
      );
      await expect(
        page
          .getByRole("article", { name: "Order" })
          .getByText("Read", { exact: true }),
      ).toBeVisible();
      expect(await overflow(page)).toBeLessThanOrEqual(0);
      await expectAccountNavDiscoverable(page, width, "Notifications");
    });
  }

  test("account nav by keyboard on the tab strip (375px): focus is visible and moves through every destination", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await signIn(page);
    await page.goto("/account/addresses");
    await expect(
      page.getByRole("heading", { level: 1, name: "Addresses" }),
    ).toBeVisible();

    const nav = page.getByRole("navigation", { name: "Account" });
    const firstLink = nav.getByRole("link", { name: "Profile" });
    await firstLink.focus();
    for (const label of NAV_LABELS) {
      const link = nav.getByRole("link", { name: label });
      await expect(link).toBeFocused();
      await expect(link).toBeInViewport();
      await expect(link).not.toHaveCSS("box-shadow", "none");
      await page.keyboard.press("Tab");
    }
    await expect(nav.getByRole("button", { name: "Log out" })).toBeFocused();
  });
});
