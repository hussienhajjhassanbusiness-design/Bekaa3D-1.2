# Real Backend Acceptance

## Phase 5A run: 2026-11-09 to 2026-11-10

| Item | Value |
|---|---|
| Frontend commit tested | `3ea70b3` (Phase 5A compatibility commit). This document is updated in the commit after it |
| Backend | `C:\My projects\Bekaa3D-backend`, branch `main`, commit **`2dfb27b`** |
| Runtime | Docker Compose: api, worker, postgres, redis, clamav all `healthy`. `CAPTCHA_PROVIDER=fake`, `EMAIL_PROVIDER=console` |
| Frontend runtime | `npm run dev` on :3000. `.env.local` (git-ignored, **no credentials**) sets `API_PROXY_TARGET=http://localhost:8000` and `MEDIA_PROXY_TARGET=http://localhost:8001` |
| Media server | dev-only read-only static server over the backend's `storage/media_public` on :8001. `npx serve` hung at package download, so a minimal Node static server was used instead (same role) |
| Method | Real browser (system Edge through Playwright) driving the real frontend, which proxies to the real backend. **No route mocking**, with one exception: the CAPTCHA_INVALID check rewrites only the outgoing `captcha_token` so the real backend gives the refusal. The mocked `npm run test:e2e` suite is separate and is **not** counted here |
| Test identities | throwaway customers `accept-<timestamp>@example.com`, created by the run itself through the real register flow. No seed credentials were used or recorded. Verify and reset tokens were read from the dev DB `email_outbox` row of the throwaway account only (the console email adapter logs payload keys, not values; tokens are stored hashed) |

**Overall: public PASS · media PASS · auth PASS · account PASS · CSRF PASS · admin NOT RUN (blocked on credentials) · VERSION_CONFLICT NOT RUN (admin-only).**

### Health and contract

| Check | Result | Evidence |
|---|---|---|
| `/api/health/live` through the frontend proxy | **PASS** | `200 {"status":"ok"}` |
| `/api/health/ready` through the frontend proxy | **PASS** | `200 {"status":"ok","version":"0.1.0","commit":"unknown"}` (the runtime does not report its own commit) |
| Running `/openapi.json` vs backend repo `docs/frontend-handoff/openapi.json` | **PASS: schema-equal** | sorted-key deep comparison is equal; bytes differ only in key order |
| Old snapshot (`d1c1cf1`) vs current: drift on pre-existing contract | 5 schemas, all fixed | `NotificationType`, `PasswordResetRequest`, `PublicSettingsRead`, `RegisterRequest`, `ResendVerificationRequest`. No pre-existing operation changed or was removed |

### Public

| Feature | Result | Evidence |
|---|---|---|
| Home (`/`) | **PASS** | real products; `/media` images loaded (`naturalWidth > 0`) |
| Shop (`/shop`) | **PASS** | real catalogue; images loaded through the frontend origin |
| Categories, materials, colours | **PASS** | filter options `Home Decor`, `PETG`, `Black` come from the backend |
| Search (`/shop?q=planter`) | **PASS** | only `geometric-planter` shown |
| Suggestions | **PASS** | typing `pla` gave `GET /api/v1/search/suggestions` → 200; "Geometric Planter" shown |
| Product detail (`/shop/geometric-planter`) | **PASS** | heading plus real image (see environment note 2) |
| About (`/about`) | **PASS** | renders |
| Public settings | **PASS** | keys exactly `accepting_orders, cash_max_order_total, cash_payment_enabled, pickup_address, pickup_hours, whatsapp_number`; no `free_shipping_threshold`; `cash_max_order_total = {amount_cents: 10000, currency: "USD"}` |

### Media

| Check | Result | Evidence |
|---|---|---|
| Seeded product image through the **frontend origin** | **PASS** | `GET http://localhost:3000/media/products/fa6c43bc-….png` → `200 image/png`, 3053 B, PNG magic bytes. Rendered in the browser on home, shop and detail |
| Production URL semantics | unchanged | the `/media` rewrite is registered only when `MEDIA_PROXY_TARGET` is set **and** `NODE_ENV !== "production"` (`src/lib/config/proxyRewrites.test.ts`) |

### Auth

| Feature | Result | Evidence |
|---|---|---|
| Register with captcha | **PASS** | real Cloudflare Turnstile widget, test site key `1x00000000000000000000AA`, issued the dummy token; body contained `captcha_token`; `202`; enumeration-safe copy |
| Resend verification with captcha | **PASS** | body contained `captcha_token`; `202` |
| `400 CAPTCHA_INVALID` (real backend) | **PASS** | refused token → real `400 code=CAPTCHA_INVALID`; UI showed frontend-owned copy; raw `detail` not rendered |
| `503` captcha unavailable | unit-tested only | can't be forced at runtime without reconfiguring the backend's fake provider |
| Verify-email fragment-token flow | **PASS** | `/verify-email#token=…` → `POST /auth/verify-email` `204`; token removed from the address bar |
| Login → `/me` | **PASS** | login `200`; `/me` `200`; `csrf_token` cookie present; `access_token` cookie is httpOnly |
| Refresh | **PASS** | with `access_token` removed, the protected page triggered `POST /auth/refresh` → `204`, and the profile rendered again |
| Logout | **PASS (API level)** | `POST /auth/logout` with the frontend CSRF contract → `204`; `/me` then `401`; `/account/profile` redirects to `/login`. **No mounted UI control calls logout** (defect 7) |
| Password-reset request with captcha | **PASS** | body contained `captcha_token`; `202` |
| Reset-password fragment-token flow | **PASS** | `/reset-password#token=…`, token sanitized from the URL; confirm `204`; login with the new password `200` |
| Real `429 RATE_LIMITED` | observed | after about 5 reset requests from one IP within minutes, the backend answered `429` (correct limiter behaviour, triggered by repeated acceptance runs) |

### Account

| Feature | Result | Evidence |
|---|---|---|
| Profile (`/account/profile`) | **PASS** | real account email rendered from `/me` |
| Notifications list | **PASS** | one `custom_request` notification inserted for the throwaway account renders with the new "Custom request" label |
| Mark read / mark unread | **PASS** | `PATCH /me/notifications/{id}` `200` both ways; button state toggled |

### Error contract

| Check | Result | Evidence |
|---|---|---|
| `403 CSRF_INVALID` | **PASS** | `PATCH /me/notifications/{id}` with a wrong `X-CSRF-Token` → real `403 code=CSRF_INVALID` |
| `409 VERSION_CONFLICT` | **NOT RUN** | in the current OpenAPI it exists only on admin products (`POST`/`PATCH`/`DELETE /admin/products…`); needs the admin session |

### Admin

| Feature | Result |
|---|---|
| MFA login, settings, customers, categories/materials/colours, product list/detail/edit, product create/update/delete, image upload/alt/cover/order/delete, admin CSRF, `409 VERSION_CONFLICT` (API and edit UI) | **NOT RUN: blocked on credentials.** The dev seed credentials are treated as compromised and must not enter source, tests, docs, `.env.local` or logs. A ready script reads them from a local file outside any repo (`%USERPROFILE%\.bekaa3d\dev-admin.json`: `admin_email`, `admin_password`, `admin_totp_secret`), types them only into the real login form, and never prints them. The file was not present when the run was attempted |

### Integration defects found

1. **Captcha missing on three mounted auth flows** (register, resend, reset request): every real submit was `422`. **Fixed**; real runtime now `202`.
2. **`PublicSettingsRead` type drift** (removed `free_shipping_threshold`; missing `cash_payment_enabled`, `cash_max_order_total`). **Fixed.**
3. **`NotificationType` lacked `custom_request`**: generic fallback label only. **Fixed**; real notification renders "Custom request".
4. **No `/media` in local dev.** **Fixed** with the dev-only `MEDIA_PROXY_TARGET` rewrite.
5. **Mocked E2E race:** two login tests asserted `/account$` while `/account` server-redirects to `/account/profile`. They failed on the pre-change baseline too. **Fixed** (test-only).
6. **Hydration mismatch on `/reset-password`** (open, frontend): the server renders the invalid-link alert because the token exists only in the URL fragment, and the client renders the form. React recovers on the client and the flow works, but it logs a hydration error. Not contract drift, so not changed in this phase.
7. **No logout control in the mounted UI** (open, frontend): `AuthProvider.logout()` exists but nothing calls it. Not contract drift, so not changed in this phase.
8. Observation (backend): `/health/ready` reports `commit: "unknown"`.
9. Observation (backend): login succeeded for an account before its email was verified. Confirm with the backend team that this is intended.

### Environment notes

1. Partway through, Claude Code stopped the dev and media servers because the machine was critically low on memory. They were restarted after the user said to continue.
2. After that reclaim, the surviving orphan dev server's render workers were gone (`Jest worker encountered 2 child process exceptions`), so dynamic `/shop/[slug]` returned 500. A fresh dev server fixed it, and product detail passed on that server. This was not a code defect.
3. Acceptance scripts were kept outside the repo, in the session scratchpad. Script bugs found during the run (outbox template names; a cookie re-add that dropped the `/api/v1/auth`-scoped refresh cookie; an early URL-sanitization assertion) were fixed and the affected items re-run. The results above are from the fixed runs.

---

## Earlier attempt: 2026-10-19 (blocked)

Frontend `53b1ef3`, no backend checkout and no Docker on the machine, so the real-runtime portion was not attempted. That blocker is gone (see above).
