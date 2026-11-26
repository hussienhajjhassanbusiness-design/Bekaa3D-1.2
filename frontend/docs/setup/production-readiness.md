# Bekaa3D Production Readiness (frontend)

Status as of phase 6F (2026-11-12): frontend `master`, backend `main` at `2dfb27b`. Nothing here has been deployed; no hosting, DNS or provider has been chosen. This document is the checklist for whoever does that.

> ## ⚠️ REAL ONLINE PAYMENT IS NOT BUILT
>
> The only online payment provider is the backend's **`mock`** (backend VS-032, the real provider, is not built). The backend refuses to boot with `PAYMENT_PROVIDER=mock` in `ENVIRONMENT=production` (`payments/infrastructure/providers/factory.py`), and a production build of this frontend never sends a shopper to a `mock` provider's page (`src/lib/checkout/paymentProviderGuard.ts`; the shopper sees "the payment page isn't available, nothing has been charged").
>
> **Until VS-032 ships, a public deployment can sell only through cash on delivery or pickup** (physical items), with the backend on `PAYMENT_PROVIDER=none`, so online checkout answers `503 ONLINE_PAYMENT_UNAVAILABLE` and the frontend shows "Online payment isn't available right now". **STL files and accepted offers can only be paid online, so they cannot be sold** until a real provider exists. Never present the mock provider as a live payment method. Set `NEXT_PUBLIC_ALLOW_MOCK_PAYMENTS=true` only in a non-public staging build.

## 1. Production topology

The browser must see **one origin**. Cookies are same-origin (`SameSite=Lax`), CSRF is double-submit against that origin, and the frontend only ever calls relative `/api/...` and `/media/...` paths. Nothing in the browser knows the backend's address.

```
Browser ── HTTPS ──▶ reverse proxy (public origin, TLS, HSTS, body limit)
                      ├── /api/health/*  ─▶ backend  /health/*      (strip /api)
                      ├── /api/*         ─▶ backend  /api/*          (keep /api; up to 52,494,336-byte bodies)
                      ├── /media/*       ─▶ backend MEDIA_PUBLIC_DIR (static files, read-only)
                      └── everything else ─▶ Next.js (`next start`, :3000)

backend (uvicorn :8000) ── Postgres 16, Redis 7, ClamAV
worker  (arq)           ── same image, same env: email outbox, offer expiry, reminders, payment jobs
```

- **Route `/api/*` to the backend directly at the proxy. Do not rely on Next.js to proxy the API in production.** Next buffers at most 10 MB of a rewritten request body (`experimental.proxyClientMaxBodySize`) and forwards a larger one truncated, so Bring Your Idea uploads above 10 MB would hang (found in phase 6B, `REAL-BACKEND-ACCEPTANCE.md`). Raising that limit destabilised the dev server and was reverted; it must not be re-added. With the proxy routing `/api` itself, leave `API_PROXY_TARGET` unset in the production build.
- **Keep the two `/api` rules in this order:** `/api/health/` first (the backend's health routes have no `/api` prefix), then `/api/`.
- **`/media/*`** is the backend's `MEDIA_PUBLIC_URL=/media`, files under `MEDIA_PUBLIC_DIR` (product images, already re-encoded by the backend). Serve them as static files with `X-Content-Type-Options: nosniff`. No dev media server (`MEDIA_PROXY_TARGET`) exists in a production build; that rewrite is never compiled in.
- Private files (`STL_PRIVATE_DIR`, `UPLOADS_PRIVATE_DIR`) must **never** be served by the proxy. The backend streams the only private download (admin BYI attachments) itself. `XACCEL_PREFIX=/protected` is configured in the backend but no route in `2dfb27b` uses it; keep any `/protected` location `internal`.
- STL files are delivered **manually by email** (ADR-019). There is no customer download route to expose.

### Example nginx server block

A sketch, not a tested config: adapt names, paths and certificates.

```nginx
server {
    listen 443 ssl http2;
    server_name shop.example.com;

    # ssl_certificate / ssl_certificate_key ...
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Bring Your Idea: 5 images x 10 MiB + 64 KiB of fields = 52,494,336 bytes.
    # 51m = 53,477,376 bytes.
    client_max_body_size 51m;

    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Request-ID      $request_id;

    location /api/health/ {
        proxy_pass http://backend:8000/health/;
    }

    location /api/ {
        proxy_pass http://backend:8000;    # no URI part: /api/... is kept
        # Uploads are malware-scanned and re-encoded before the 201, and the
        # client waits up to 180 s; checkout waits on the provider.
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_request_buffering on;
    }

    location /media/ {
        alias /data/media_public/;
        add_header X-Content-Type-Options nosniff always;
        expires 7d;
    }

    location /protected/ {
        internal;
    }

    location / {
        proxy_pass http://frontend:3000;
    }
}

server {
    listen 80;
    server_name shop.example.com;
    return 301 https://$host$request_uri;
}
```

## 2. Environment variables

### Frontend (`.env.local.example` is the canonical list)

| Variable | Kind | Development | Production |
|---|---|---|---|
| `API_PROXY_TARGET` | server-only, **build time** (compiled into the rewrites) | required, e.g. `http://localhost:8000` | **unset** when the proxy routes `/api` (recommended) |
| `MEDIA_PROXY_TARGET` | server-only, development only | optional static server for `/media` | ignored; never compiled in |
| `NEXT_PUBLIC_TURNSTILE_SITE_KEY` | public, **inlined at build** | optional; falls back to Cloudflare's test key | **required**; no fallback (forms show "Verification is unavailable") |
| `NEXT_PUBLIC_ALLOW_MOCK_PAYMENTS` | public, **inlined at build** | not needed (mock allowed outside production builds) | **unset** (or anything but `true`); `true` only for a non-public staging build |
| `NODE_ENV` | set by Next | `next dev` | `next build` / `next start` |

No frontend variable is a secret. Because public values are inlined and rewrites are compiled, **build per environment**; a build cannot be retargeted by changing variables at `next start`.

### Backend (owned by the backend; listed for the deployment checklist)

From backend `.env.example`: `ENVIRONMENT=production` (this alone turns on `Secure` cookies, refuses the mock provider and the fake captcha/scanner), `DEBUG=false`, `BASE_URL`, `FRONTEND_BASE_URL` (the public origin: email links point at it), `DATABASE_URL`, `REDIS_URL`, `JWT_SIGNING_KEY`, `CSRF_SECRET`, `IP_HASH_SALT`, `PHONE_HASH_SALT`, `MFA_SECRET_KEY`, storage paths (`STORAGE_ROOT`, `STL_PRIVATE_DIR`, `UPLOADS_PRIVATE_DIR`, `MEDIA_PUBLIC_DIR`, `MEDIA_PUBLIC_URL=/media`), `SCANNER=clamav` with `CLAMAV_HOST`/`CLAMAV_PORT`, `PAYMENT_PROVIDER=none` (until VS-032), `EMAIL_PROVIDER` / `EMAIL_PROVIDER_KEY` / `EMAIL_FROM` (not `console`), `CAPTCHA_PROVIDER=turnstile` with `TURNSTILE_SECRET` (the pair of the frontend's site key), `SENTRY_DSN` (optional), `LOG_LEVEL`, `APP_VERSION`, `GIT_COMMIT_SHA`. Every secret is generated per environment and lives only in the backend's secret store.

## 3. Cookies, HTTPS and proxy headers

| Cookie | `HttpOnly` | `Secure` | `SameSite` | `Path` |
|---|---|---|---|---|
| `access_token` (15 min) | yes | when `ENVIRONMENT` ≠ development | Lax | `/` |
| `refresh_token` (30 days) | yes | same | Lax | `/api/v1/auth` |
| `csrf_token` (30 days, read by JS for `X-CSRF-Token`) | no | same | Lax | `/` |

(Backend `src/app/api/cookies.py`; verified in the 6F production smoke, where the local backend is `development`, so `Secure` was off as designed.)

- **HTTPS everywhere.** With `ENVIRONMENT=production` the cookies are `Secure`, so plain HTTP cannot sign in. Redirect port 80 to 443 and send HSTS from the proxy (this frontend deliberately does not send HSTS).
- **Same origin.** `/api` must be on the same host as the pages, or the `Lax` cookies and the CSRF double-submit break. No CORS is configured or needed.
- **Real client IPs.** The backend rate-limits (login throttling, register, contact, BYI, per-IP limits) by `request.client.host`. Behind a proxy, uvicorn must trust the proxy's `X-Forwarded-For`: run it with `--proxy-headers --forwarded-allow-ips=<proxy address>` (or `FORWARDED_ALLOW_IPS`). Without it every visitor shares the proxy's IP bucket, and one busy hour locks everyone out of registration. **This is a backend deployment setting; the backend image's `CMD` does not set it today.**
- Pass `X-Forwarded-Proto` and `X-Request-ID`; the backend echoes `X-Request-ID` and logs it.

## 4. Security headers

Sent by Next on every route (`src/lib/config/securityHeaders.ts`, wired in `next.config.ts`; `poweredByHeader: false`):

| Header | Value |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` (payment providers and WhatsApp learn only the origin) |
| `X-Frame-Options` | `DENY` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=(), usb=(), payment=(), interest-cohort=()` |
| `Content-Security-Policy` (production builds only) | `default-src 'self'; script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; font-src 'self' data:; connect-src 'self'; frame-src https://challenges.cloudflare.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'` |
| `Strict-Transport-Security` | **from the reverse proxy** (see the nginx sketch) |

- **Turnstile** needs exactly `script-src` and `frame-src` `https://challenges.cloudflare.com`; verified in production mode (the widget's iframe rendered, no CSP violation).
- **Payment redirects** are top-level navigations to the provider's `redirect_url`, which CSP does not restrict. When VS-032 adds a real provider, check whether it needs a `frame-src` or `form-action` entry.
- **Media** is same-origin; `img-src https:` keeps product images working if a deployment serves `/media` from a separate HTTPS origin.
- FOLLOW-UP: `script-src 'unsafe-inline'` remains because the App Router's bootstrap scripts are inline. A nonce-based CSP needs middleware and dynamic rendering of every page.
- If the proxy also sets any of these headers, make sure it does not send a second, conflicting CSP.

## 5. Large Bring Your Idea uploads

- Contract (backend `2dfb27b`): up to 5 images of up to 10 MiB each plus fields, a body of at most **52,494,336 bytes**, with `Content-Length`. Each file is malware-scanned (ClamAV) and re-encoded synchronously before the `201`.
- The proxy must allow at least that body on `/api/` (`client_max_body_size 51m` in nginx) and allow time for the scan (`proxy_read_timeout` ≥ 180 s; the client gives up at 180 s).
- The request must **not** pass through Next (see section 1). ClamAV must be healthy: with the scanner down, uploads answer `503 SERVICE_UNAVAILABLE`, which the form shows as a safe retry message.

## 6. Observability

- The frontend has no third-party script or telemetry. Problem `title`/`detail`/`msg` are never shown; every visible error is frontend copy.
- `app/error.tsx` writes the error to the browser console **only outside production builds**. In production a server-side render failure keeps its `digest` in the Next server log (`next start` stdout); correlate API failures by the backend's `X-Request-ID` / `request_id`.
- No frontend log contains a token, password, phone or address (tokens are read from the URL fragment and removed from the address bar; nothing is written to browser storage).
- Recommendations, not installed: ship `next start` stdout and the backend's JSON logs to one log store; uptime checks on `/api/health/live` and `/api/health/ready` through the public origin; alert on `5xx` rate, on `ready` failing, on ClamAV health and on email-outbox `failed` rows; optional backend `SENTRY_DSN`. A frontend error-reporting SDK would need a `connect-src` entry in the CSP.

## 7. Production build and start (verified locally in 6F)

```bash
npm ci
NEXT_PUBLIC_TURNSTILE_SITE_KEY=<site key> npm run build    # API_PROXY_TARGET unset behind the proxy
npm run start                                              # :3000; the proxy sends non-/api, non-/media traffic here
```

The 6F local smoke ran `next build` + `next start` against the local backend (`API_PROXY_TARGET` set only because no reverse proxy existed locally) over 36 routes as a visitor, a customer and an MFA administrator: every route rendered its `h1`; 0 CSP violations, 0 page errors, 0 API `5xx`; Turnstile rendered under the CSP with the test key and failed safe with no key. Product images 404 locally, as expected without a `/media` server.

## 8. Deployment checklist

**Services**
- [ ] Postgres 16 (managed or with backups), Redis 7, ClamAV (`clamav/clamav:stable`, signatures updating), backend API (uvicorn), backend **worker** (`python -m app.worker`, same image and env; required for email, offer expiry and reminders, payment jobs), Next.js (`next start`), reverse proxy with TLS.

**Backend**
- [ ] `ENVIRONMENT=production`, `DEBUG=false`, every secret generated for this environment.
- [ ] `alembic upgrade head` before the new API version starts (backend README "Migrations"). Never run `scripts/dev_seed.py` (it refuses outside development/test).
- [ ] `PAYMENT_PROVIDER=none` until VS-032. `CAPTCHA_PROVIDER=turnstile` with `TURNSTILE_SECRET`. `SCANNER=clamav`. A real `EMAIL_PROVIDER`.
- [ ] `FRONTEND_BASE_URL` = the public origin (email links), `MEDIA_PUBLIC_URL=/media`.
- [ ] uvicorn trusts the proxy's forwarded headers (section 3).
- [ ] Create the first administrator and complete MFA enrolment; keep the recovery codes offline.
- [ ] Open the shop deliberately: `accepting_orders` defaults to **closed** on a fresh deployment; set cash, pickup address/hours and the WhatsApp number in Admin → Settings.

**Frontend**
- [ ] Build per environment with `NEXT_PUBLIC_TURNSTILE_SITE_KEY` (the real key whose secret is in the backend). `API_PROXY_TARGET` unset. `NEXT_PUBLIC_ALLOW_MOCK_PAYMENTS` unset.
- [ ] Run `npm run lint`, `typecheck`, `test`, `build` and `test:e2e` on the commit being deployed.

**Proxy, HTTPS, security**
- [ ] TLS certificate with renewal; 80 → 443; HSTS.
- [ ] The routes of section 1 in that order; `/api` body limit ≥ 52,494,336 bytes and read timeout ≥ 180 s.
- [ ] `/media` static and read-only; private storage never exposed; `/protected` internal.
- [ ] Response headers present (`curl -I https://<site>/`); no duplicate CSP.

**Data**
- [ ] Database backups (scheduled, encrypted, restore tested) and backups of `MEDIA_PUBLIC_DIR`, `STL_PRIVATE_DIR` and `UPLOADS_PRIVATE_DIR`. Redis holds rate limits and the mock provider's state only; it need not be backed up.

**Health and smoke checks after every deploy**
- [ ] `GET https://<site>/api/health/live` → `200`; `GET https://<site>/api/health/ready` → `200` with the expected `version` and `commit`.
- [ ] Backend `scripts/smoke/vs012_post_deploy.sh https://<site>` (read-only).
- [ ] Browser: home, `/shop`, a product page, `/login` (Turnstile renders), `/contact` and `/bring-your-idea` (widget renders), sign in as a test customer (`/account/*`, `/cart`, `/checkout` shows online payment unavailable while `PAYMENT_PROVIDER=none`), admin sign-in with MFA (`/admin/orders`, `/admin/offers`). No console CSP errors.

**Rollback**
- [ ] Keep the previous frontend build (or image) and backend image; roll back by redeploying them. Frontend builds are stateless.
- [ ] Database migrations are forward-only in practice: take a backup before `alembic upgrade`, and roll back the schema only with a tested `alembic downgrade` or by restoring that backup.
- [ ] Because public variables are inlined, a rollback uses the old **build**, not the old variables.

## 9. Known limitations before public production

1. **No real online payment provider** (backend VS-032). STL products and accepted offers cannot be paid. See the banner at the top.
2. **Legal review pending** for the consent and checkout copy (`src/lib/checkout/checkoutCopy.ts` marks it "PENDING LEGAL REVIEW"), terms of sale, privacy policy and the STL final-sale wording.
3. **Not built in the backend** (so not in the frontend): reviews (VS-036/037), the analytics dashboard beyond the wishlist and BYI funnel endpoints (VS-043), data export (VS-044) and account deletion (VS-045).
4. CSP keeps `'unsafe-inline'` scripts (section 4, FOLLOW-UP).
5. `isFollowableRedirect` accepts `http:` payment URLs so the local mock works; restrict it to `https:` when the real provider lands (FOLLOW-UP with VS-032).
