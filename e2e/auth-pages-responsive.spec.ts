import { test, expect, type Page } from "@playwright/test";
import { stubEmptyCart } from "./support/stubCart";
import { stubGuest } from "./support/stubGuest";
import { routeFakeTurnstile, waitForCaptchaToken } from "./support/fakeTurnstile";

// Redesign Batch 4 — every auth surface in the shared Stitch auth card, at
// the six QA widths. Asserts user-facing layout only: one visible h1 clear of
// the sticky 64px header, no horizontal overflow, every form control inside
// the viewport, and (on captcha pages) room for the provider's 300px frame.
//
// The fake Turnstile script renders no frame of its own, so the test inserts
// a 300x65 box into the widget container — the size of the real widget —
// before measuring. Route interception only; no backend.

const WIDTHS = [320, 375, 768, 1024, 1280, 1440];

interface AuthRoute {
  path: string;
  heading: RegExp;
  captcha: boolean;
}

const ROUTES: AuthRoute[] = [
  { path: "/login", heading: /log in/i, captcha: false },
  { path: "/register", heading: /create your account/i, captcha: true },
  { path: "/forgot-password", heading: /reset your password/i, captcha: true },
  // A syntactically present token: the form state (never submitted here).
  { path: "/reset-password#token=e2e-layout-only", heading: /reset your password/i, captcha: false },
  // No token: the invalid-link state, reached locally without any request.
  { path: "/verify-email", heading: /verify your email/i, captcha: false },
  { path: "/verify-email/resend", heading: /resend verification email/i, captcha: true },
];

test.beforeEach(async ({ page }) => {
  await stubEmptyCart(page);
  await stubGuest(page);
  await routeFakeTurnstile(page);
});

async function simulateRealCaptchaFrame(page: Page) {
  await waitForCaptchaToken(page);
  await page.evaluate(() => {
    const container = document.querySelector('[data-testid="captcha-widget"]');
    const frame = document.createElement("div");
    frame.setAttribute("data-e2e-frame", "true");
    frame.style.width = "300px";
    frame.style.height = "65px";
    container?.appendChild(frame);
  });
}

for (const route of ROUTES) {
  test(`${route.path}: auth card fits ${WIDTHS.join("/")}px with one visible h1 and no overflow`, async ({ page }) => {
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(route.path);

      const heading = page.getByRole("heading", { level: 1 });
      await expect(heading).toHaveCount(1);
      await expect(heading).toHaveText(route.heading);
      await expect(heading).toBeVisible();
      expect((await heading.boundingBox())!.y, `${width}px: h1 under the sticky header`).toBeGreaterThanOrEqual(64);

      if (route.captcha) {
        await simulateRealCaptchaFrame(page);
        const frame = (await page.locator('[data-e2e-frame="true"]').boundingBox())!;
        expect(frame.x, `${width}px: captcha frame clipped on the left`).toBeGreaterThanOrEqual(0);
        expect(frame.x + frame.width, `${width}px: captcha frame clipped on the right`).toBeLessThanOrEqual(width);
      }

      const [scrollWidth, clientWidth] = await page.evaluate(() => [
        document.documentElement.scrollWidth,
        document.documentElement.clientWidth,
      ]);
      expect(scrollWidth, `${width}px: horizontal overflow`).toBeLessThanOrEqual(clientWidth);

      for (const control of await page.locator("main input, main button, main a").all()) {
        if (!(await control.isVisible())) {
          continue;
        }
        const box = (await control.boundingBox())!;
        expect(box.x, `${width}px: control off the left edge`).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width, `${width}px: control off the right edge`).toBeLessThanOrEqual(width + 0.5);
      }
    }
  });
}
