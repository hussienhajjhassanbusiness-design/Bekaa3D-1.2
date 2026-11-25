import { test, expect, type Page, type Route } from "@playwright/test";
import { stubEmptyWishlist } from "./support/stubCart";
import { E2E_ORIGIN } from "./support/origin";

// Homepage hero image — an admin replaces it in Store Settings → the
// storefront homepage shows the new image; with none set, the default brand
// visual shows.
//
// A deterministic, in-memory stand-in for the real contract (backend
// docs/homepage-hero-image.md, openapi.json): GET /api/v1/home/hero-image,
// PUT /api/v1/admin/home/hero-image (multipart `file`, CSRF), and the stored
// file served under /media. The real backend's run is in
// docs/backend-handoff/REAL-BACKEND-ACCEPTANCE.md.

const CSRF = "e2e-csrf-value";
const ADMIN = {
  id: "admin-1",
  email: "admin@example.com",
  role: "admin",
  email_verified: true,
  email_verified_at: "2025-01-01T00:00:00Z",
  created_at: "2024-01-01T00:00:00Z",
};

// A real 2×2 PNG, so the browser actually decodes the served image.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGPkTZZmYGBgYmBgYGBgAAAGoACPlJGwEgAAAABJRU5ErkJggg==",
  "base64"
);

interface Fake {
  heroKey: string | null;
  puts: { csrf: string | undefined; hasFile: boolean }[];
  rejectNext: boolean;
  patches: { value: unknown; csrf: string | undefined }[];
  failNextPatch: boolean;
}

function heroUrl(fake: Fake): string | null {
  return fake.heroKey ? `/media/${fake.heroKey}` : null;
}

function settingRow(key: string, type: string, value: unknown) {
  return {
    key,
    type,
    value,
    description: null,
    unit: null,
    minimum: null,
    maximum: null,
    nullable: true,
    is_public: false,
    updated_at: "2026-11-25T00:00:00Z",
    updated_by: null,
  };
}

async function install(page: Page): Promise<Fake> {
  const fake: Fake = { heroKey: null, puts: [], rejectNext: false, patches: [], failNextPatch: false };
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  await page.context().addCookies([{ name: "csrf_token", value: CSRF, url: E2E_ORIGIN }]);
  await stubEmptyWishlist(page);
  await page.route(/\/api\/v1\/me$/, (r) => json(r, ADMIN));
  await page.route(/\/api\/v1\/notifications(\?.*)?$/, (r) =>
    json(r, { items: [], next_cursor: null, unread_count: 0 })
  );
  await page.route(/\/api\/v1\/settings\/public$/, (r) =>
    json(r, {
      accepting_orders: true,
      cash_payment_enabled: false,
      cash_max_order_total: { amount_cents: 10000, currency: "USD" },
      pickup_address: null,
      pickup_hours: null,
      whatsapp_number: null,
    })
  );
  await page.route(/\/api\/v1\/(categories|materials|colours)(\?.*)?$/, (r) => json(r, { items: [] }));
  await page.route(/\/api\/v1\/products(\?.*)?$/, (r) => json(r, { items: [], next_cursor: null }));
  await page.route(/\/api\/v1\/promotions$/, (r) => json(r, { items: [] }));
  await page.route(/\/api\/v1\/admin\/settings(\?.*)?$/, (r) =>
    json(r, {
      items: [
        settingRow("accepting_orders", "boolean", true),
        settingRow("homepage_hero_image", "string", fake.heroKey),
      ],
      next_cursor: null,
    })
  );
  await page.route(/\/api\/v1\/home\/hero-image$/, (r) => json(r, { url: heroUrl(fake) }));
  // The existing settings PATCH: like the real backend, it accepts only null for this key.
  await page.route(/\/api\/v1\/admin\/settings\/homepage_hero_image$/, (route) => {
    const request = route.request();
    expect(request.method()).toBe("PATCH");
    const { value } = request.postDataJSON() as { value: unknown };
    fake.patches.push({ value, csrf: request.headers()["x-csrf-token"] });
    if (fake.failNextPatch) {
      fake.failNextPatch = false;
      return json(route, { type: "about:blank", title: "Unavailable", status: 503, code: "SERVICE_UNAVAILABLE" }, 503);
    }
    if (value !== null) {
      return json(route, { type: "about:blank", title: "Invalid", status: 422, code: "SETTING_INVALID" }, 422);
    }
    fake.heroKey = null;
    return json(route, settingRow("homepage_hero_image", "string", null));
  });
  await page.route(/\/api\/v1\/admin\/home\/hero-image$/, async (route) => {
    const request = route.request();
    expect(request.method()).toBe("PUT");
    const body = request.postDataBuffer()?.toString("latin1") ?? "";
    fake.puts.push({ csrf: request.headers()["x-csrf-token"], hasFile: /name="file"; filename="/.test(body) });
    if (fake.rejectNext) {
      fake.rejectNext = false;
      return json(
        route,
        { type: "about:blank", title: "Upload rejected", status: 422, code: "UPLOAD_REJECTED", detail: "too small" },
        422
      );
    }
    fake.heroKey = `home/hero/${String(fake.puts.length).padStart(32, "a")}.png`;
    return json(route, { url: heroUrl(fake) });
  });
  await page.route(/\/media\/home\/hero\/[0-9a-f]{32}\.png$/, (r) =>
    r.fulfill({ status: 200, contentType: "image/png", body: PNG })
  );
  return fake;
}

const heroVisual = (page: Page) => page.locator("[data-hero-visual]");

async function chooseHeroFile(page: Page, name: string, mimeType: string, buffer: Buffer) {
  await page.getByLabel("Hero image").setInputFiles({ name, mimeType, buffer });
}

test.describe("Homepage hero image", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("with none set, the homepage keeps the default brand visual", async ({ page }) => {
    await install(page);
    await page.goto("/");

    await expect(heroVisual(page)).toHaveAttribute("data-hero-visual", "default");
    await expect(heroVisual(page).locator('img[src="/brand/bekaa3d-mark.png"]')).toBeVisible();
  });

  test("admin replaces the hero image in Store Settings → the storefront homepage shows it", async ({ page }) => {
    const fake = await install(page);

    await page.goto("/admin/settings");
    const homepage = page.getByRole("region", { name: "Homepage" });
    await expect(homepage.getByText("Default brand visual (no image uploaded)")).toBeVisible();
    await expect(page.getByRole("button", { name: "Save changes" })).toBeDisabled();

    await chooseHeroFile(page, "eid-hero.png", "image/png", PNG);
    await expect(homepage.getByRole("img", { name: "Preview of the new hero image" })).toBeVisible();
    await expect(homepage.getByText("New image — not saved yet")).toBeVisible();
    expect(fake.puts).toHaveLength(0);

    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Settings saved." })).toBeVisible();
    expect(fake.puts).toEqual([{ csrf: CSRF, hasFile: true }]);
    const saved = heroUrl(fake)!;

    // A refresh reads it back from the backend.
    await page.reload();
    await expect(
      page.getByRole("region", { name: "Homepage" }).getByRole("img", { name: "Current hero image" })
    ).toHaveAttribute("src", saved);

    await page.goto("/");
    await expect(heroVisual(page)).toHaveAttribute("data-hero-visual", "custom");
    const image = heroVisual(page).locator("img");
    await expect(image).toHaveAttribute("src", saved);
    await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
    await expect(image).toHaveCSS("object-fit", "cover");
    const box = (await heroVisual(page).boundingBox())!;
    expect(Math.abs(box.width - box.height)).toBeLessThan(2);
    // The floating cards stay.
    const side = heroVisual(page).locator("xpath=..");
    await expect(side.getByText("Made to order", { exact: true })).toBeVisible();
    await expect(side.getByText("Print it yourself", { exact: true })).toBeVisible();
  });

  test("a wrong file is refused before upload, and a refused upload keeps the saved image", async ({ page }) => {
    const fake = await install(page);
    fake.heroKey = `home/hero/${"b".repeat(32)}.png`;
    const saved = heroUrl(fake)!;

    await page.goto("/admin/settings");
    const homepage = page.getByRole("region", { name: "Homepage" });
    await chooseHeroFile(page, "notes.txt", "text/plain", Buffer.from("not an image"));
    await expect(homepage.getByRole("alert")).toContainText("isn't a supported file type");
    await expect(page.getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(fake.puts).toHaveLength(0);

    fake.rejectNext = true;
    await chooseHeroFile(page, "tiny.png", "image/png", PNG);
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(homepage.getByRole("alert")).toContainText("Your current hero image is unchanged.");
    await expect(page.getByRole("status").filter({ hasText: "Settings saved." })).toHaveCount(0);
    expect(fake.puts).toHaveLength(1);

    await page.goto("/");
    await expect(heroVisual(page).locator("img")).toHaveAttribute("src", saved);
  });

  test("admin restores the default visual → the storefront homepage shows it again", async ({ page }) => {
    const fake = await install(page);
    fake.heroKey = `home/hero/${"d".repeat(32)}.png`;
    const saved = heroUrl(fake)!;

    await page.goto("/admin/settings");
    const homepage = page.getByRole("region", { name: "Homepage" });
    await expect(homepage.getByRole("img", { name: "Current hero image" })).toHaveAttribute("src", saved);

    // Preview only: nothing is sent, and Discard brings the saved image back.
    await homepage.getByRole("button", { name: "Restore default" }).click();
    await expect(homepage.getByText("Default brand visual — not saved yet")).toBeVisible();
    await expect(homepage.getByRole("img", { name: "Default brand visual" })).toBeVisible();
    await page.getByRole("button", { name: "Discard changes" }).click();
    await expect(homepage.getByRole("img", { name: "Current hero image" })).toHaveAttribute("src", saved);
    expect(fake.patches).toHaveLength(0);

    // A failed save keeps the pending restore; the retry applies it.
    fake.failNextPatch = true;
    await homepage.getByRole("button", { name: "Restore default" }).click();
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(homepage.getByRole("alert")).toContainText("Your current hero image is unchanged.");
    await expect(homepage.getByText("Default brand visual — not saved yet")).toBeVisible();
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Settings saved." })).toBeVisible();
    expect(fake.patches).toEqual([
      { value: null, csrf: CSRF },
      { value: null, csrf: CSRF },
    ]);
    expect(fake.puts).toHaveLength(0);

    await page.reload();
    await expect(
      page.getByRole("region", { name: "Homepage" }).getByText("Default brand visual (no image uploaded)")
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Restore default" })).toHaveCount(0);

    await page.goto("/");
    await expect(heroVisual(page)).toHaveAttribute("data-hero-visual", "default");
    await expect(heroVisual(page).locator('img[src="/brand/bekaa3d-mark.png"]')).toBeVisible();
  });
});

test.describe("Homepage hero image on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the hero keeps its phone layout: heading and CTAs, no visual panel, no sideways scroll", async ({ page }) => {
    const fake = await install(page);
    fake.heroKey = `home/hero/${"c".repeat(32)}.png`;
    await page.goto("/");

    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("link", { name: "Shop Now" })).toBeVisible();
    await expect(heroVisual(page)).toBeHidden();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
