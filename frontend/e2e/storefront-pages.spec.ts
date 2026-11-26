import { test, expect, type Page } from "@playwright/test";
import { stubGuest } from "./support/stubGuest";

// Redesign Batch 3 — Home, Shop and Product Detail at every supported
// width, the shop filter drawer, the skip link and the WhatsApp floating
// action. Route interception only; contract-shaped fixtures; no backend.

const CATEGORIES = [
  { id: "cat-1", name: "Toys and Figures", slug: "toys-figures" },
  { id: "cat-2", name: "Engineering Parts", slug: "engineering" },
];

function productItem(overrides: Record<string, unknown> = {}) {
  return {
    id: "p1",
    type: "physical",
    name: "Articulated Dragon",
    slug: "dragon",
    cover_image: null,
    price: { amount_cents: 1800, currency: "USD" },
    category: CATEGORIES[0],
    material: { id: "mat-1", name: "PLA" },
    colour: { id: "col-1", name: "Red" },
    is_available: true,
    purchase_mode: "both",
    average_rating: 0,
    review_count: 0,
    is_featured: true,
    ...overrides,
  };
}

const ITEMS = [
  productItem(),
  productItem({ id: "p2", slug: "gear", name: "Planetary Gear Set", type: "stl", purchase_mode: null }),
  productItem({ id: "p3", slug: "vase", name: "Voronoi Lattice Vase With A Deliberately Long Product Name For Wrapping" }),
  productItem({ id: "p4", slug: "intake", name: "Air Intake", is_available: false }),
];

const DETAIL = {
  ...productItem(),
  description: "A fully articulated dragon print.",
  images: [
    { id: "i1", url: "/media/products/dragon-1.png", alt_text: "Dragon, front", is_cover: true },
    { id: "i2", url: "/media/products/dragon-2.png", alt_text: "Dragon, side", is_cover: false },
  ],
  seo_title: null,
  seo_description: null,
  og_image_url: null,
  dimensions: { length_mm: 120, width_mm: 80, height_mm: 60 },
  production_lead_time_days: 2,
  batch_size: 2,
  max_quantity_per_line: 5,
  capabilities: { can_add_to_cart: true, can_offer: false, whatsapp_available: true },
};

async function mockCatalogue(page: Page, whatsappNumber: string | null = "+96170000000") {
  await stubGuest(page);
  await page.route(/\/api\/v1\/categories$/, (route) => route.fulfill({ body: JSON.stringify({ items: CATEGORIES }) }));
  await page.route(/\/api\/v1\/materials$/, (route) => route.fulfill({ body: JSON.stringify({ items: [{ id: "mat-1", name: "PLA" }] }) }));
  await page.route(/\/api\/v1\/colours$/, (route) => route.fulfill({ body: JSON.stringify({ items: [{ id: "col-1", name: "Red" }] }) }));
  await page.route(/\/api\/v1\/products(\?.*)?$/, (route) => route.fulfill({ body: JSON.stringify({ items: ITEMS, next_cursor: null }) }));
  await page.route(/\/api\/v1\/products\/dragon$/, (route) => route.fulfill({ body: JSON.stringify(DETAIL) }));
  await page.route("**/api/v1/settings/public", (route) =>
    route.fulfill({
      body: JSON.stringify({
        accepting_orders: true,
        cash_payment_enabled: true,
        cash_max_order_total: { amount_cents: 10000, currency: "USD" },
        pickup_address: null,
        pickup_hours: null,
        whatsapp_number: whatsappNumber,
      }),
    })
  );
}

async function expectNoHorizontalOverflow(page: Page) {
  const [scrollWidth, clientWidth] = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    document.documentElement.clientWidth,
  ]);
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
}

const WIDTHS = [320, 375, 768, 1024, 1280, 1440];

test.describe("Storefront pages (redesign batch 3)", () => {
  for (const width of WIDTHS) {
    test(`home, shop and product detail at ${width}px: no overflow, one h1, usable card widths`, async ({ page }) => {
      await mockCatalogue(page);
      await page.setViewportSize({ width, height: 900 });

      await page.goto("/");
      await expect(page.getByRole("heading", { level: 1, name: "Bekaa3D — Engineered Grade 3D Solutions" })).toBeVisible();
      await expect(page.getByRole("heading", { level: 2, name: "Featured Products" })).toBeVisible();
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
      await expectNoHorizontalOverflow(page);

      await page.goto("/shop");
      const firstCard = page.getByRole("link", { name: /^(?!Sign in to save).*Articulated Dragon/ });
      await expect(firstCard).toBeVisible();
      // Fewer, well-sized cards: never squeezed below ~260px.
      expect((await firstCard.boundingBox())!.width).toBeGreaterThanOrEqual(260);
      const filtersButton = page.getByRole("button", { name: /^Filters/ });
      const aside = page.getByRole("complementary", { name: "Filters" });
      if (width >= 1024) {
        await expect(aside).toBeVisible();
        await expect(filtersButton).toBeHidden();
      } else {
        await expect(aside).toBeHidden();
        await expect(filtersButton).toBeVisible();
      }
      await expectNoHorizontalOverflow(page);

      await page.goto("/shop/dragon");
      await expect(page.getByRole("heading", { level: 1, name: "Articulated Dragon" })).toBeVisible();
      await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toBeVisible();
      await expectNoHorizontalOverflow(page);
    });
  }

  test("shop drawer (768px): keyboard open, focus inside, a ticked filter updates the URL and survives close/reopen", async ({ page }) => {
    await mockCatalogue(page);
    await page.setViewportSize({ width: 768, height: 900 });
    await page.goto("/shop");

    const trigger = page.getByRole("button", { name: /^Filters/ });
    await trigger.focus();
    await page.keyboard.press("Enter");
    const drawer = page.getByRole("dialog", { name: "Filters" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("button", { name: "Close filters" })).toBeFocused();
    await expect(page.locator("html")).toHaveCSS("overflow", "hidden");

    // URL-controlled checkbox (as in the aside): click, then wait for the URL.
    await drawer.getByRole("checkbox", { name: "Toys and Figures" }).click();
    await expect(page).toHaveURL(/category=cat-1/);
    await expect(drawer).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();
    await expect(page.getByRole("button", { name: "Filters, 1 active" })).toBeFocused();

    await page.getByRole("button", { name: "Filters, 1 active" }).click();
    await expect(drawer.getByRole("checkbox", { name: "Toys and Figures" })).toBeChecked();
    await drawer.getByRole("button", { name: "Show results" }).click();
    await expect(drawer).toBeHidden();
    await expect(page).toHaveURL(/category=cat-1/);
  });

  test("shop drawer (375px): fits the viewport, clear filters works through the same handler", async ({ page }) => {
    await mockCatalogue(page);
    await page.setViewportSize({ width: 375, height: 740 });
    await page.goto("/shop?category=cat-1");

    await page.getByRole("button", { name: "Filters, 1 active" }).click();
    const drawer = page.getByRole("dialog", { name: "Filters" });
    const box = await drawer.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(375);
    await expectNoHorizontalOverflow(page);

    await drawer.getByRole("button", { name: "Clear filters" }).click();
    await expect(page).not.toHaveURL(/category=/);
    await expect(drawer.getByRole("checkbox", { name: "Toys and Figures" })).not.toBeChecked();
  });

  test("product detail: gallery thumbnails switch the main image from the keyboard; specs are term/definition pairs", async ({ page }) => {
    await mockCatalogue(page);
    await page.goto("/shop/dragon");

    const main = page.getByTestId("product-gallery-main-image");
    await expect(main).toHaveAttribute("alt", "Dragon, front");
    await page.getByRole("button", { name: "Dragon, side" }).focus();
    await page.keyboard.press("Enter");
    await expect(main).toHaveAttribute("alt", "Dragon, side");
    await expect(page.getByRole("button", { name: "Dragon, side" })).toHaveAttribute("aria-current", "true");

    await expect(page.getByRole("term")).toHaveText(["Material", "Colour", "Dimensions", "Production lead time"]);
    await expect(page.getByRole("link", { name: "Toys and Figures" })).toHaveAttribute("href", "/shop?category=cat-1");
  });

  test("skip link: first Tab shows it above the sticky header, Enter moves focus to main", async ({ page }) => {
    await mockCatalogue(page);
    await page.goto("/shop");

    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: "Skip to main content" });
    await expect(skip).toBeFocused();
    const box = await skip.boundingBox();
    expect(box!.height).toBeGreaterThanOrEqual(44);
    // It is the topmost element at its own centre (painted over the header).
    const topmost = await page.evaluate(
      ([x, y]) => document.elementFromPoint(x!, y!)?.textContent ?? "",
      [box!.x + box!.width / 2, box!.y + box!.height / 2]
    );
    expect(topmost).toContain("Skip to main content");

    await page.keyboard.press("Enter");
    await expect(page.getByRole("main")).toBeFocused();
  });

  test("WhatsApp floating action: accessible fill, 56px target, under the header and above the footer's last line", async ({ page }) => {
    await mockCatalogue(page);
    await page.setViewportSize({ width: 375, height: 740 });
    await page.goto("/");

    const fab = page.getByRole("link", { name: "Chat with us on WhatsApp" });
    await expect(fab).toBeVisible();
    await expect(fab).toHaveCSS("background-color", "rgb(18, 140, 126)");
    await expect(fab).toHaveCSS("color", "rgb(255, 255, 255)");
    const box = await fab.boundingBox();
    expect(box!.width).toBe(56);
    expect(box!.x + box!.width).toBeLessThanOrEqual(375);
    expect(Number(await fab.evaluate((el) => getComputedStyle(el).zIndex))).toBeLessThan(40);

    // At the very bottom of the page the footer's last line stays clear of it.
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    const tagline = page.getByRole("contentinfo").getByText("Engineered Grade 3D Solutions");
    const taglineBox = await tagline.boundingBox();
    const fabBox = await fab.boundingBox();
    expect(taglineBox!.y + taglineBox!.height).toBeLessThanOrEqual(fabBox!.y);

    await fab.focus();
    await expect(fab).not.toHaveCSS("box-shadow", "none");
  });

  test("home: CTA panel and section links go to real routes", async ({ page }) => {
    await mockCatalogue(page);
    await page.goto("/");

    await expect(page.getByRole("main").getByRole("link", { name: "Bring your idea" })).toHaveAttribute("href", "/bring-your-idea");
    await expect(page.getByRole("link", { name: "Contact us" })).toHaveAttribute("href", "/contact");
    await expect(page.getByRole("link", { name: /View all products/ })).toHaveAttribute("href", "/shop");
    await expect(page.getByRole("link", { name: /Shop all products/ })).toHaveAttribute("href", "/shop");
    await expect(page.getByRole("link", { name: /Engineering Parts/ })).toHaveAttribute("href", "/shop?category=cat-2");
  });
});
