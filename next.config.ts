import type { NextConfig } from "next";
import { buildProxyRewrites } from "./src/lib/config/proxyRewrites";

const nextConfig: NextConfig = {
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
