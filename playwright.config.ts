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
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "smoke",
      testMatch: ["smoke.spec.ts", "register-and-verify.spec.ts", "login-session.spec.ts", "account-profile.spec.ts"],
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
  },
});
