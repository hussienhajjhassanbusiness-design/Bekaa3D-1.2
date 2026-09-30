import { test, expect } from "@playwright/test";

// FVS001-T16 — the default, deterministic, backend-independent E2E suite
// (§23/§27 risk #11). Must pass whether or not a real VS-001 backend is
// running. Never asserts a specific backend/readiness state — see the
// dedicated tolerance test below. This is the ONLY spec the "smoke"
// Playwright project matches (see playwright.config.ts); backend
// connectivity has its own separate spec and script.

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
    // time. This never asserts which one — only that at most one status
    // region and at most one alert region exist (no duplicate live
    // regions), and that if either is present, its text is one of the
    // known, valid copies rather than an unexpected/broken render.
    const statusCount = await page.getByRole("status").count();
    const alertCount = await page.getByRole("alert").count();
    expect(statusCount).toBeLessThanOrEqual(1);
    expect(alertCount).toBeLessThanOrEqual(1);

    if (statusCount + alertCount > 0) {
      const region = statusCount > 0 ? page.getByRole("status").first() : page.getByRole("alert").first();
      await expect(region).toHaveText(
        /Loading…|reachable but not ready yet|could not be reached|readiness check timed out/
      );
    }
  });
});
