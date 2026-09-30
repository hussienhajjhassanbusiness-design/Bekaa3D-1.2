import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // FVS-001-IMPLEMENTATION-PLAN.md §9/§12/§13, corrected at FVS-002 BATCH 2
  // Part B — forward the browser's same-origin /api/:path* requests to the
  // real backend, server-side, so the browser never learns the backend's
  // origin. API_PROXY_TARGET is a local-developer convenience, not a hard
  // requirement — a clean checkout with no .env.local must still build.
  // Registering no rewrite at all when it's unset avoids ever constructing
  // an invalid "undefined/:path*" destination or inventing a hard-coded
  // fallback backend origin.
  //
  // Two backend path shapes now exist (FVS-002-IMPLEMENTATION-PLAN.md §1
  // row 1, §5): the health endpoints' real backend path has NO "/api"
  // prefix (/health/live, /health/ready), while the versioned auth
  // endpoints' real backend path KEEPS its "/api" prefix
  // (/api/v1/auth/register, etc.) — confirmed directly from the backend
  // contract, not inferred. A plain array of rewrites is Next's "afterFiles"
  // list and is tried in source order, first match wins (see
  // node_modules/next/dist/docs/.../rewrites.md, "Path Matching"/"order
  // routes are checked"), so the more specific health rule is listed first
  // and matches before the general rule ever sees a health request.
  async rewrites() {
    const target = process.env.API_PROXY_TARGET;
    if (!target) {
      return [];
    }

    return [
      {
        source: "/api/health/:path*",
        destination: `${target}/health/:path*`,
      },
      {
        source: "/api/:path*",
        destination: `${target}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
