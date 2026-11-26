import type { NextConfig } from "next";
import { buildProxyRewrites } from "./src/lib/config/proxyRewrites";
import { buildSecurityHeaders } from "./src/lib/config/securityHeaders";

// E2E harness only (playwright.config.ts sets BEKAA3D_E2E_BUILD=1 for its
// own `next build` + `next start`). The mocked Playwright suite runs against
// a production build compiled with test-only public values (the Turnstile
// always-pass test key, the mock-payment opt-in). Writing that build to its
// own directory keeps it from ever replacing the real `npm run build` output
// in .next/, and its own tsconfig receives the type globs Next appends for a
// custom distDir, so the tracked tsconfig.json never changes. This flag
// changes only WHERE the build goes, never what the app does.
const e2eBuildConfig: Partial<NextConfig> =
  process.env.BEKAA3D_E2E_BUILD === "1"
    ? { distDir: ".next-e2e", typescript: { tsconfigPath: "tsconfig.e2e.json" } }
    : {};

const nextConfig: NextConfig = {
  ...e2eBuildConfig,
  // Phase 6F: no `X-Powered-By: Next.js` fingerprint.
  poweredByHeader: false,
  // Phase 6F: security headers on every route; the CSP only in a production
  // build (src/lib/config/securityHeaders.ts).
  async headers() {
    return [{ source: "/:path*", headers: buildSecurityHeaders({ nodeEnv: process.env.NODE_ENV }) }];
  },
  // FVS-001-IMPLEMENTATION-PLAN.md §9/§12/§13 (corrected at FVS-002 BATCH 2):
  // forward the browser's same-origin /api/:path* requests to the real
  // backend, server-side, so the browser never learns the backend's origin.
  // API_PROXY_TARGET is a local-developer convenience, not a hard
  // requirement — a clean checkout with no .env.local must still build, so
  // no rule is registered when it is unset (never an "undefined/:path*"
  // destination, never a hard-coded fallback origin).
  //
  // Rule order and the development-only /media rule are documented and
  // unit-tested in src/lib/config/proxyRewrites.ts.
  async rewrites() {
    return buildProxyRewrites({
      apiTarget: process.env.API_PROXY_TARGET,
      mediaTarget: process.env.MEDIA_PROXY_TARGET,
      nodeEnv: process.env.NODE_ENV,
    });
  },
};

export default nextConfig;
