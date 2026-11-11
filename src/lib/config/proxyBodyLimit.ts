// Phase 6B-2 — the same-origin /api proxy (next.config.ts rewrites) buffers a
// request body only up to `experimental.proxyClientMaxBodySize` (default
// 10 MB). A larger body is silently cut short while its Content-Length still
// promises the whole thing, so the backend waits and the request hangs.
// The largest body the backend accepts is a Bring Your Idea submission:
// 5 images x 10 MB + 64 KB of multipart framing and text fields (backend
// 2dfb27b engagement/api/custom_requests.py MAX_BODY_BYTES). The proxy must
// pass at least that much; the backend still enforces its own limits.
const MAX_ATTACHMENTS = 5;
const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;
const MULTIPART_ALLOWANCE = 64 * 1024;

export const PROXY_MAX_BODY_BYTES = MAX_ATTACHMENTS * MAX_ATTACHMENT_BYTES + MULTIPART_ALLOWANCE;
