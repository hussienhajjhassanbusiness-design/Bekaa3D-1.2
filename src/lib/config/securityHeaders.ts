// #SECURITY-HEADERS (phase 6F)
//
// Response headers for every route, wired in next.config.ts `headers()`.
//
// Always sent: nosniff, a strict referrer policy (a payment provider or
// WhatsApp only ever learns the origin, never a path or query), no framing
// (also `frame-ancestors 'none'` in the CSP), and a Permissions-Policy that
// turns off powerful features the shop never uses.
//
// Content-Security-Policy is sent only by a PRODUCTION build: the dev server
// needs `eval` and a websocket for Fast Refresh. Its only third-party origin
// is Cloudflare Turnstile (the widget script and its iframe). Everything
// else is same-origin by design: the browser calls /api and /media on this
// origin and never learns the backend's address. `connect-src 'self'`.
// Payment redirects are top-level navigations, which CSP does not govern.
//
// `script-src` keeps 'unsafe-inline' because the App Router's streamed
// bootstrap scripts are inline; a nonce would need middleware and fully
// dynamic rendering (FOLLOW-UP in docs/setup/production-readiness.md).
// `img-src` allows https: so product media still loads if a deployment
// serves /media from a separate HTTPS origin; images cannot run script.
//
// HSTS is deliberately NOT sent from here: TLS terminates at the reverse
// proxy, which must send Strict-Transport-Security (see the deployment doc).

export const TURNSTILE_ORIGIN = "https://challenges.cloudflare.com";

export interface SecurityHeader {
  key: string;
  value: string;
}

export function buildContentSecurityPolicy(): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'unsafe-inline' ${TURNSTILE_ORIGIN}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https:",
    "font-src 'self' data:",
    "connect-src 'self'",
    `frame-src ${TURNSTILE_ORIGIN}`,
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ].join("; ");
}

export function buildSecurityHeaders({ nodeEnv }: { nodeEnv: string | undefined }): SecurityHeader[] {
  const headers: SecurityHeader[] = [
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), usb=(), payment=(), interest-cohort=()" },
  ];
  if (nodeEnv === "production") {
    headers.push({ key: "Content-Security-Policy", value: buildContentSecurityPolicy() });
  }
  return headers;
}
