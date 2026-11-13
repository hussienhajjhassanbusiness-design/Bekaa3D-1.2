import { defineConfig, devices } from "@playwright/test";
import { E2E_ORIGIN, E2E_PORT } from "./e2e/support/origin";

// E2E HARNESS STABILIZATION (between redesign Batch 3 and Batch 4): the suite
// runs against a PRODUCTION build (`next build` + `next start`), not
// `next dev`. Under `next dev`, the first request to each route compiles it
// on demand; with many parallel workers that compile latency pushed mocked
// /me session reads past the app's request timeout ("We couldn't verify your
// session") in specs that always pass alone. A production build compiles
// every route up front, so request timing reflects the app, not the bundler.
//
// The build is the harness's own (next.config.ts BEKAA3D_E2E_BUILD=1 ->
// .next-e2e/), compiled with the test-only public values below, so it never
// replaces the real `npm run build` output in .next/. E2E_REUSE_BUILD=1
// skips the build and serves the existing .next-e2e/ — only valid when
// nothing under src/ (or the env below) changed since that build.
const reuseBuild = process.env.E2E_REUSE_BUILD === "1";
const serverCommand = reuseBuild
  ? `npm run start -- --port ${E2E_PORT}`
  : `npm run build && npm run start -- --port ${E2E_PORT}`;

// FVS001-T16 — two deliberately separate projects, not one config that
// happens to match both files. `npm run test:e2e` runs only "smoke" (via
// --project=smoke); `npm run test:e2e:backend` runs only
// "backend-connectivity" (via --project=backend-connectivity). Each
// project's own testMatch is the actual isolation mechanism — proven by
// running each command and observing which spec file it reports, not
// assumed from the file names alone (see the T16 report).
//
// Both projects share one webServer: the connectivity spec still needs a
// real Next.js server running so its request to /api/health/ready goes
// through the genuine next.config.ts rewrite (API_PROXY_TARGET, compiled into
// the build's routes manifest), not a mock.
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
  // than patching individual tests. (Measured under the former `next dev`
  // harness; kept unchanged when E2E moved to a production build.)
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: E2E_ORIGIN,
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
        "auth-pages-responsive.spec.ts",
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
    command: serverCommand,
    url: E2E_ORIGIN,
    // Never reuse: :3100 is reserved for this harness, so anything already
    // listening there is a stale or foreign server whose build/env is
    // unknown. Playwright then fails fast ("already used") instead of
    // silently testing the wrong thing. Playwright owns the process tree it
    // starts and stops it when the run ends.
    reuseExistingServer: false,
    // Covers a cold `next build` plus server start.
    timeout: 300_000,
    stdout: "ignore",
    stderr: "pipe",
    // Applies to both `next build` and `next start`. Process env wins over
    // .env.local (@next/env only fills undefined keys), so these are exact.
    env: {
      // Build into .next-e2e/ with its own tsconfig (see next.config.ts).
      BEKAA3D_E2E_BUILD: "1",
      // Mocked E2E must not depend on the dev-only /media static server
      // (:8001). A production build never registers the /media rule anyway
      // (buildProxyRewrites); the explicit empty value keeps that true even
      // if the rule's gating ever changes. No spec asserts on image bytes.
      MEDIA_PROXY_TARGET: "",
      // A production build never falls back to the Turnstile test key
      // (turnstileConfig.ts), so captcha forms would render "Verification
      // is unavailable". Inline Cloudflare's public always-pass TEST key.
      // The browser never loads the real widget: e2e/support/fakeTurnstile.ts
      // fulfils challenges.cloudflare.com with an offline fake.
      NEXT_PUBLIC_TURNSTILE_SITE_KEY: "1x00000000000000000000AA",
      // A production build refuses to send a shopper to the `mock` payment
      // provider (paymentProviderGuard.ts) unless this staging opt-in is
      // inlined. The mocked checkout/offer/payment specs exercise exactly
      // that flow against route-intercepted responses — no payment service.
      NEXT_PUBLIC_ALLOW_MOCK_PAYMENTS: "true",
    },
  },
});
