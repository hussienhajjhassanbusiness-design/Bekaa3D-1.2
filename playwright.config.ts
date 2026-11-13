import { defineConfig, devices } from "@playwright/test";

const PORT = 3000;
const BASE_URL = `http://localhost:${PORT}`;

// FVS001-T16 — two deliberately separate projects, not one config that
// happens to match both files. `npm run test:e2e` runs only "smoke" (via
// --project=smoke); `npm run test:e2e:backend` runs only
// "backend-connectivity" (via --project=backend-connectivity). Each
// project's own testMatch is the actual isolation mechanism — proven by
// running each command and observing which spec file it reports, not
// assumed from the file names alone (see the T16 report).
//
// Both projects share one webServer: the connectivity spec still needs the
// real Next.js dev server running so its request to /api/health/ready goes
// through the genuine next.config.ts rewrite, not a mock.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  // REAL STOREFRONT INTEGRATION — PHASE 1 follow-up: this machine's single
  // Next dev server, serving 14 parallel workers' client-side navigations
  // at once, occasionally pushes a post-click `toHaveURL` assertion past
  // the 5s default under CPU contention — every affected test (new and
  // pre-existing alike) passes in under 2s standalone or with --workers=1,
  // so this is resource contention, not a functional defect. Raising the
  // default assertion timeout absorbs that contention uniformly rather
  // than patching individual tests.
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "smoke",
      testMatch: [
        "smoke.spec.ts",
        "register-and-verify.spec.ts",
        "login-session.spec.ts",
        "account-profile.spec.ts",
        "shop.spec.ts",
        "product-detail.spec.ts",
        "auth-account-phase2.spec.ts",
        "admin-routes.spec.ts",
        "account-addresses.spec.ts",
        "cart.spec.ts",
        "checkout.spec.ts",
        "account-orders.spec.ts",
        "payment-result.spec.ts",
        "account-order-actions.spec.ts",
        "admin-orders.spec.ts",
        "admin-payments.spec.ts",
        "admin-operations.spec.ts",
        "contact.spec.ts",
        "bring-your-idea.spec.ts",
        "offers.spec.ts",
        "wishlist.spec.ts",
        "storefront-chrome.spec.ts",
        "storefront-pages.spec.ts",
      ],
      // Uses the system-installed Microsoft Edge (Chromium-based) via
      // Playwright's "channel" option instead of Playwright's own bundled
      // Chromium — this sandboxed environment has no outbound network
      // access to cdn.playwright.dev to download a browser binary, but a
      // channel-based browser launches an already-installed executable
      // directly, with no download required. See the T16 report for the
      // exact error this substitutes for.
      use: { ...devices["Desktop Edge"], channel: "msedge" },
    },
    {
      name: "backend-connectivity",
      testMatch: "backend-connectivity.spec.ts",
      use: { ...devices["Desktop Edge"], channel: "msedge" },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    // Mocked E2E must not depend on the dev-only /media static server
    // (MEDIA_PROXY_TARGET, normally :8001 via .env.local). An explicit empty
    // value wins over .env.local (@next/env only fills undefined keys) and
    // buildProxyRewrites registers no /media rule for it, so /media/*
    // resolves to Next's own local 404 instead of ECONNREFUSED proxy noise.
    // No spec asserts on loaded image bytes; production media semantics are
    // untouched (that rule never exists in a production build). Only
    // applies when Playwright starts the server itself (not a reused one).
    env: { MEDIA_PROXY_TARGET: "" },
  },
});
