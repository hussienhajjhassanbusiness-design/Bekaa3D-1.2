import { test, expect } from "@playwright/test";

// FVS001-T16 — the default, deterministic, backend-independent E2E suite
// (§23/§27 risk #11). Must pass whether or not a real VS-001 backend is
// running. Never asserts a specific backend/readiness state — see the
// dedicated tolerance test below. This is the ONLY spec the "smoke"
// Playwright project matches (see playwright.config.ts); backend
// connectivity has its own separate spec and script.
//
// FVS-022 follow-up — `/` is now the real Bekaa3D home surface
// (HeroSection only, no fetched data), not the FVS-001 placeholder.
// The heading assertions below still use the exact same approved
// tagline text (HeroSection's own default), so they were left
// unmodified; new tests below prove the placeholder paragraph is gone
// and that no dead/fabricated content was introduced in its place.

test.describe("Frontend smoke (FVS001-T16)", () => {
  test("/ boots the composed shell with foundation content, landmarks, and SkipLink", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("banner")).toBeVisible();
    await expect(page.getByRole("main")).toBeVisible();
    await expect(page.getByRole("contentinfo")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Bekaa3D — Engineered Grade 3D Solutions" })
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "Skip to main content" })).toBeAttached();
  });

  test("an unknown route renders 404 content with a working link back to /", async ({ page }) => {
    await page.goto("/does-not-exist");

    await expect(page.getByRole("heading", { name: "404 — Page not found" })).toBeVisible();
    await expect(page.getByText(/doesn.t exist or may have been moved/i)).toBeVisible();

    const backHome = page.getByRole("link", { name: "Back to home" });
    await expect(backHome).toHaveAttribute("href", "/");

    await backHome.click();
    await expect(page).toHaveURL(/\/$/);
    await expect(
      page.getByRole("heading", { name: "Bekaa3D — Engineered Grade 3D Solutions" })
    ).toBeVisible();

    // The composed shell still exists exactly once after client-side
    // navigation, not duplicated by the route transition.
    await expect(page.getByRole("banner")).toHaveCount(1);
    await expect(page.getByRole("main")).toHaveCount(1);
    await expect(page.getByRole("contentinfo")).toHaveCount(1);
  });

  test("/ no longer renders the retired FVS-001 placeholder paragraph", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/FVS-001 frontend foundation slice/i)).toHaveCount(0);
  });

  test("/ links to the now-real /shop and /about routes, and still exposes no dead Bring Your Idea/Contact CTA — those routes don't exist yet", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByRole("link", { name: "Shop Now" })).toHaveAttribute("href", "/shop");
    await expect(page.getByRole("link", { name: "Learn More" })).toHaveAttribute("href", "/about");
    await expect(page.getByRole("link", { name: /bring your idea/i })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /^contact$/i })).toHaveCount(0);
  });

  test("/ renders the static Why Choose Bekaa3D section alongside the Hero heading", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
    await expect(page.getByRole("heading", { name: "Why Choose Bekaa3D" })).toBeVisible();
  });

  test("the readiness banner, whatever it shows, never breaks the shell — no specific backend state is required", async ({
    page,
  }) => {
    await page.goto("/");

    // Shell integrity holds regardless of backend availability/timing.
    await expect(page.getByRole("banner")).toHaveCount(1);
    await expect(page.getByRole("main")).toHaveCount(1);
    await expect(page.getByRole("contentinfo")).toHaveCount(1);

    // Tolerant per §23/§27 risk #11: the dev-only banner may be in any of
    // T13a's valid states (initial loading, ready/no banner, not-ready,
    // unreachable, timeout) depending on real backend availability at test
    // time. This never asserts which one. FVS-022 follow-up: the home
    // page's own FeaturedProductsSection can legitimately show a second,
    // independent `role="status"` region (its loading skeleton,
    // LoadingSpinner's shared "Loading…" text) at the same time as the
    // banner — so the cap is 2 status regions, not 1, but every matched
    // status/alert region's text must still be one of the known, valid
    // copies, never an unexpected/broken render.
    // Next.js itself always renders a hidden `#__next-route-announcer__`
    // live region with role="alert" for its own client-navigation
    // announcements — a framework internal, not app content, and often
    // empty — so it's excluded here rather than asserted against; this
    // test only cares about regions this app's own code renders.
    const status = page.getByRole("status");
    // `.filter({ hasNot })` only excludes an element whose OWN subtree
    // contains a match — the announcer div matches `getByRole("alert")`
    // itself (not as a descendant), so `hasNot` never excludes it. A CSS
    // `:not()` on the same locator excludes the element itself instead.
    const alert = page.locator('[role="alert"]:not(#__next-route-announcer__)');
    const statusCount = await status.count();
    const alertCount = await alert.count();
    expect(statusCount).toBeLessThanOrEqual(2);
    expect(alertCount).toBeLessThanOrEqual(1);

    const validText = /Loading…|reachable but not ready yet|could not be reached|readiness check timed out/;
    for (let i = 0; i < statusCount; i++) {
      await expect(status.nth(i)).toHaveText(validText);
    }
    for (let i = 0; i < alertCount; i++) {
      await expect(alert.nth(i)).toHaveText(validText);
    }
  });
});

test.describe("Home hero responsive check (FVS-022 follow-up)", () => {
  const VIEWPORTS = [320, 375, 768, 1024, 1440, 1920];

  for (const width of VIEWPORTS) {
    test(`no horizontal overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/", { waitUntil: "networkidle" });

      const [scrollWidth, clientWidth] = await page.evaluate(() => [
        document.documentElement.scrollWidth,
        document.documentElement.clientWidth,
      ]);
      expect(scrollWidth).toBeLessThanOrEqual(clientWidth);

      await expect(
        page.getByRole("heading", { level: 1, name: "Bekaa3D — Engineered Grade 3D Solutions" })
      ).toBeVisible();
    });
  }
});
