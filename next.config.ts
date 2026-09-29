import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // FVS-001-IMPLEMENTATION-PLAN.md §9/§12/§13 — the only rewrite this
  // slice needs: forward the browser's same-origin /api/:path* requests to
  // the real backend, server-side, so the browser never learns the
  // backend's origin. API_PROXY_TARGET is a local-developer convenience
  // (§12), not a hard requirement — a clean checkout with no .env.local
  // must still build. Registering no rewrite at all when it's unset avoids
  // ever constructing an invalid "undefined/:path*" destination or
  // inventing a hard-coded fallback backend origin.
  async rewrites() {
    const target = process.env.API_PROXY_TARGET;
    if (!target) {
      return [];
    }

    return [
      {
        source: "/api/:path*",
        destination: `${target}/:path*`,
      },
    ];
  },
};

export default nextConfig;
