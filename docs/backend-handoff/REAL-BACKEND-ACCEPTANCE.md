# Real Backend Acceptance

## Phase 5A run: 2026-11-09 (**partial, paused**)

| Item | Value |
|---|---|
| Frontend commit tested | working tree on top of `d7dff02`, i.e. the Phase 5A compatibility commit that adds this document |
| Backend | `C:\My projects\Bekaa3D-backend`, branch `main`, commit **`2dfb27b`** |
| Runtime | Docker Compose: api, worker, postgres, redis, clamav all `healthy`. `CAPTCHA_PROVIDER=fake`, `EMAIL_PROVIDER=console` |
| Frontend runtime | `npm run dev` on :3000. `.env.local` (git-ignored, no credentials) sets `API_PROXY_TARGET=http://localhost:8000` and `MEDIA_PROXY_TARGET=http://localhost:8001` |
| Media server | dev-only read-only static server over the backend's `storage/media_public` on :8001. `npx serve` hung at package download, so a minimal Node static server was used instead |
| Method | Real browser (system Edge through Playwright) driving the real frontend. **No route mocking**, with one exception: the CAPTCHA_INVALID check rewrites only the outgoing `captcha_token`, so the real backend gives the refusal. The mocked `npm run test:e2e` suite is separate and is **not** counted here |

**Why paused:** partway through the run, Claude Code stopped the Next dev server and the media server because the machine was critically low on memory. They were not restarted automatically. The items marked **NOT RUN** below still need a run.

### Health and contract

| Check | Result | Evidence |
|---|---|---|
| `/api/health/live` through the frontend proxy | **PASS** | `200 {"status":"ok"}` |
| `/api/health/ready` through the frontend proxy | **PASS** | `200 {"status":"ok","version":"0.1.0","commit":"unknown"}` (the runtime does not report its own commit) |
| Running `/openapi.json` vs backend repo `docs/frontend-handoff/openapi.json` | **PASS: schema-equal** | deep comparison with sorted keys is equal. Bytes differ only in key order (the export script uses `sort_keys`) |
| Old snapshot (`d1c1cf1`) vs current: drift on pre-existing contract | 5 schemas only | `NotificationType`, `PasswordResetRequest`, `PublicSettingsRead`, `RegisterRequest`, `ResendVerificationRequest` (descriptions ignored). No pre-existing operation changed or was removed |

### Public

| Feature | Result | Evidence |
|---|---|---|
| Home (`/`) | **PASS** | real products rendered; 2 `/media` images loaded (`naturalWidth > 0`) |
| Shop (`/shop`) | **PASS** | real catalogue; 9 images loaded through the frontend origin |
| Categories, materials, colours | **PASS** | filter options `Home Decor`, `PETG`, `Black` come from the backend |
| Search (`/shop?q=planter`) | **PASS** | only `geometric-planter` shown |
| Suggestions | **PASS** | typing `pla` gave `GET /api/v1/search/suggestions` → 200, and "Geometric Planter" was shown |
| Product detail (`/shop/geometric-planter`) | **PASS** | heading plus real image |
| About (`/about`) | **PASS** | renders |
| Public settings | **PASS** | `200`, keys exactly `accepting_orders, cash_max_order_total, cash_payment_enabled, pickup_address, pickup_hours, whatsapp_number`; no `free_shipping_threshold`; `cash_max_order_total = {amount_cents: 10000, currency: "USD"}` |
| Page errors | none | no uncaught page errors during the run |

### Media

| Check | Result | Evidence |
|---|---|---|
| Seeded product image through the **frontend origin** | **PASS** | `GET http://localhost:3000/media/products/fa6c43bc-….png` → `200 image/png`, 3053 B, PNG magic bytes. Images render in the browser on home, shop and detail |
| Production URL semantics | unchanged | the `/media` rewrite is registered only when `MEDIA_PROXY_TARGET` is set **and** `NODE_ENV !== "production"` (unit-tested in `src/lib/config/proxyRewrites.test.ts`) |

### Auth (throwaway customer created during the run; no seed credentials used)

| Feature | Result | Evidence |
|---|---|---|
| Register with captcha | **PASS** | the real Cloudflare Turnstile widget (test site key `1x00000000000000000000AA`) issued the dummy token; request body contained `captcha_token`; backend `202`; enumeration-safe success copy |
| Resend verification with captcha | **PASS** | body contained `captcha_token`; `202` |
| `400 CAPTCHA_INVALID` (real backend) | **PASS** | refused token → real `400 code=CAPTCHA_INVALID`; UI showed the frontend-owned copy; raw `detail` not rendered |
| `503` captcha unavailable | unit-tested only | cannot be forced at runtime without reconfiguring the backend's fake provider |
| Verify-email fragment-token flow | **NOT RUN** | first attempt failed because of an acceptance-script bug (wrong outbox template name `verify_email`; the real one is `verification_email`). Script fixed, not re-run |
| Login → `/me` | **PASS** | `POST /auth/login` 200; `GET /me` 200; `csrf_token` cookie present; `access_token` cookie is httpOnly. Note: login succeeded before email verification |
| Refresh | **NOT RUN** | first attempt returned 401 because of a script bug: it re-added cookies filtered by URL `/`, which dropped the `/api/v1/auth`-scoped `refresh_token`. Script fixed, not re-run |
| Logout | **NOT RUN** | cascaded from the refresh script bug (session lost). Not a frontend result |
| Password-reset request with captcha | **PASS** | body contained `captcha_token`; `202` |
| Reset-password fragment-token flow | **NOT RUN** | same template-name script bug (`password_reset_email`). Script fixed, not re-run |

Tokens for the verify and reset steps are taken from the dev DB `email_outbox` row of the throwaway account only. The console email adapter logs payload keys, not values, and tokens are stored hashed.

### Account

| Feature | Result | Evidence |
|---|---|---|
| Profile (`/account/profile`) | **PASS** | real account email rendered from `/me` |
| Notifications list, mark read/unread | **NOT RUN** | cascaded from the refresh script bug. The re-run inserts one `custom_request` notification for the throwaway account to exercise the new type end to end |

### Admin

| Feature | Result |
|---|---|
| MFA login, settings, customers, reference data, product CRUD, product images | **NOT RUN.** Needs the development admin's password and TOTP secret. Per the security instruction these are treated as compromised dev credentials and must not enter source, tests, docs, `.env.local` or logs. A run needs them supplied from local secure storage, read by the acceptance script and never printed |

### Error contract

| Check | Result |
|---|---|
| `403 CSRF_INVALID` | **NOT RUN** (cascaded from the refresh script bug; the re-run sends a wrong `X-CSRF-Token` on `PATCH /me/notifications/{id}`) |
| `409 VERSION_CONFLICT` | **NOT RUN**. In the current OpenAPI it exists only on admin products (`POST`/`PATCH`/`DELETE /admin/products…`), so it needs the admin session |

### Integration defects found

1. **Captcha missing on three mounted auth flows** (register, resend, reset request): every real submit was `422`. Fixed in Phase 5A; real runtime now `202`.
2. **`PublicSettingsRead` type drift** (removed `free_shipping_threshold`; missing `cash_payment_enabled`, `cash_max_order_total`). Fixed.
3. **`NotificationType` lacked `custom_request`**: UI didn't crash (generic fallback), but the label was generic. Fixed.
4. **No `/media` route in local dev.** Fixed with a dev-only `MEDIA_PROXY_TARGET` rewrite.
5. Observation (backend, not changed): `/health/ready` reports `commit: "unknown"`.
6. Observation (backend, not changed): an unverified account could log in. Confirm with the backend team that this is intended.

---

## Earlier attempt: 2026-10-19 (blocked)

Frontend `53b1ef3`, no backend checkout and no Docker on the machine, so the real-runtime portion was not attempted. That blocker is gone (see above).
