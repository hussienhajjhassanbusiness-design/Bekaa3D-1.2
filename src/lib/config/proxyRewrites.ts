// Same-origin proxy rules used by next.config.ts's rewrites(). Pure so it
// can be unit-tested. No CORS: the browser only ever calls same-origin
// paths and Next forwards them server-side.
//
// - API_PROXY_TARGET (server-only): /api/health/* -> {target}/health/*
//   (the health endpoints have no /api prefix on the backend), then
//   /api/* -> {target}/api/*. Rewrites are tried in order, so the specific
//   health rule comes first.
// - MEDIA_PROXY_TARGET (server-only, development only): the backend API does
//   not serve /media/* locally (BACKEND-RESPONSE.md B4; backend VS-020).
//   Point this at the backend Compose stack's `media` service, which serves
//   storage/media_public read-only on http://localhost:8001. Never registered
//   in a production build: there nginx serves the same root-relative
//   /media/... paths, so production URL semantics are unchanged.
export interface ProxyRewrite {
  source: string;
  destination: string;
}

export interface ProxyRewriteInput {
  apiTarget: string | undefined;
  mediaTarget: string | undefined;
  nodeEnv: string | undefined;
}

export function buildProxyRewrites({ apiTarget, mediaTarget, nodeEnv }: ProxyRewriteInput): ProxyRewrite[] {
  const rules: ProxyRewrite[] = [];
  if (apiTarget) {
    rules.push(
      { source: "/api/health/:path*", destination: `${apiTarget}/health/:path*` },
      { source: "/api/:path*", destination: `${apiTarget}/api/:path*` }
    );
  }
  if (mediaTarget && nodeEnv !== "production") {
    rules.push({ source: "/media/:path*", destination: `${mediaTarget}/:path*` });
  }
  return rules;
}
