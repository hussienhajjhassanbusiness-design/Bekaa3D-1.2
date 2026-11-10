# Real Backend Acceptance

## Phase 5B: Address Book (FVS-023), 2026-11-10 to 2026-11-11

| Item | Value |
|---|---|
| Frontend commits tested | `87d3454` (dialog focus fix), `dda1bfc` (secondary Button, TextAreaField), `05b0fb3` (address contract layer), `7acb321` (`/account/addresses`). The run used the working tree that became these commits. After the run, only a test-only exact-text matcher in `e2e/account-addresses.spec.ts` changed. This document is updated in the commit after them |
| Backend | `C:\My projects\Bekaa3D-backend`, branch `main`, commit **`2dfb27b`** (unchanged) |
| Contract check | running `/openapi.json` == `docs/backend-handoff/openapi.json` == backend repo `docs/frontend-handoff/openapi.json` (deep-equal, all three) |
| Runtime | Docker Compose api/worker/postgres/redis/clamav `healthy`. At the start, Docker Desktop's engine was stopped (`:8000` accepted TCP but never answered); restarted with `docker desktop restart`. `npm run dev` on :3000 proxying to :8000. No media server needed |
| Method | real Edge browser through Playwright against the real frontend and backend. **No route mocking.** Temporary script kept in the session scratchpad, never committed |
| Customer identity | throwaway `accept-addr-<timestamp>@example.com` accounts made through the real register flow (real Turnstile test widget). Random passwords, never printed or stored. Verify token read only from that account's dev-DB `email_outbox` row. No seeded record was read or modified |
| Data left behind | two throwaway accounts (run 1 was discarded for script bugs, see below), each with **0 live addresses** (deleted through the UI; soft-deleted rows remain by backend design) |

**Overall: PASS, 27/27 in one run.**

### Current contract (as implemented)

| Operation | Route | Auth | Result |
|---|---|---|---|
| List | `GET /api/v1/me/addresses` | session | `200 {items: AddressRead[]}`, default first, hard-capped at 20, not paginated |
| Read one | `GET /api/v1/me/addresses/{id}` | session | `200 AddressRead`; another user's / deleted / unknown id → `404 NOT_FOUND` |
| Create | `POST /api/v1/me/addresses` | session + CSRF + verified email | `201 AddressRead`; the first live address is always the default; `422 ADDRESS_LIMIT_REACHED` at 20 |
| Edit | `PATCH /api/v1/me/addresses/{id}` | session + CSRF + verified email | `200 AddressRead`; omitted = unchanged, `null` clears `area`/`street` (null on a required field is a 422), `is_default` true/false sets/clears, empty body is a 422 |
| Delete | `DELETE /api/v1/me/addresses/{id}` | session + CSRF + verified email | `204`; soft delete; deleting the default leaves **no** default |
| Make default | `PUT /api/v1/me/addresses/{id}/default` | session + CSRF + verified email | `200 AddressRead`; the previous default is cleared atomically |

`AddressRead`: `id, label, recipient_name, phone (E.164), governorate, city, area|null, street|null, landmark_notes, is_default, created_at, updated_at`. `Governorate`: `akkar, baalbek_hermel, beirut, beqaa, keserwan_jbeil, mount_lebanon, nabatieh, north, south`. Limits: label 50, recipient_name 100, phone 32, city 100, area 100, street 200, landmark_notes 500 (required, multi-line). No zone, fee or threshold field exists (ADR-024).

### Results

| Check | Result | Evidence |
|---|---|---|
| Anonymous `/account/addresses` | **PASS** | → `/login?returnTo=%2Faccount%2Faddresses`; again after a mounted logout |
| Unverified customer write | **PASS** | warning notice + resend link shown; real `POST` → `403 EMAIL_VERIFICATION_REQUIRED`; dialog shows frontend copy; raw `detail` not on the page |
| Page load, nav | **PASS** | real `GET` `200`; "Addresses" nav link `aria-current="page"`; empty state; notice gone once verified |
| Client validation | **PASS** | empty submit shows field errors, focuses the first field, sends **no** request |
| Real `422 VALIDATION_ERROR` | **PASS** | phone `12` → `422`, `loc=body.phone`; shown on the Phone field ("Enter a Lebanese phone number…"), `aria-invalid`, focused; no `ValidationError.msg` on the page; nothing stored |
| Create (first) | **PASS** | `POST` `201`; body keys exactly the `AddressCreate` set; shown as Default (backend rule); phone `03 123 456` returned and shown as `+9613123456` |
| Refresh after create | **PASS** | street/area, city + governorate label, landmark notes and Default all persist |
| Create (second, not default) | **PASS** | `201`, `is_default=false`; blank street sent as `null`; `+961 71 123 456` → `+96171123456` |
| Edit | **PASS** | city changed + area cleared → `PATCH` body exactly `{"city":"Batroun","area":null}` → `200` |
| Refresh after edit | **PASS** | "Batroun, North"; area gone |
| Edit with no changes | **PASS** | no request sent; "No changes to save." |
| Set as default | **PASS** | `PUT …/default` `200`; badge moves after the refetch; server list default-first; persists across reload |
| Clear default via edit | **PASS** | untick → `PATCH {"is_default":false}` `200` → no default anywhere (UI + server) |
| Set default via edit | **PASS** | tick → `PATCH {"is_default":true}` `200` |
| CSRF on UI writes | **PASS** | the 8 UI writes made before this check (4 POST including the refused 403/422 ones, 3 PATCH, 1 PUT) all carried `X-CSRF-Token` equal to the `csrf_token` cookie. The two later UI `DELETE`s answered `204`, which the backend's CSRF check only allows with a valid token |
| CSRF enforcement | **PASS** | wrong/missing token on `POST`, `PATCH`, `PUT …/default`, `DELETE` → all `403 CSRF_INVALID`; state unchanged |
| Unknown id | **PASS** | `GET` and `DELETE` → `404 NOT_FOUND` |
| Read one | **PASS** | `GET /me/addresses/{id}` equals the list's record |
| Delete: cancel | **PASS** | Cancel sends nothing |
| Delete | **PASS** | confirm → `DELETE` `204` → dialog closes → gone after reload |
| Delete the default | **PASS** | dialog warns "you won't have a default address…"; `204`; empty list after reload (no promotion) |
| 375px + keyboard | **PASS** | no horizontal overflow (page or dialog); dialog opens focused on Label; Escape closes it and focus returns to the trigger |
| Runtime errors | **PASS** | no page errors, no hydration errors |

Not exercised against the real backend: `422 ADDRESS_LIMIT_REACHED` (needs 20 addresses; unit + component tested) and a real cross-user `404` (only an unknown id was used; the backend gives one 404 for all three cases).

### Defects found and fixed

11. **Dialog focus not restored after the address form auto-focuses** (fixed in `87d3454`, frontend). Found by the new mocked E2E. `DialogShell` recorded the trigger in a passive effect, after the child had already moved focus to its first field, so the input became the "trigger". It now records in a layout effect, and `AddressForm` focuses its first field in an effect instead of `autoFocus`. Regression test in `DialogShell.test.tsx`.
- Stale pre-contract address model (`{id, displayLines, isDefault}`, drift audit §5): replaced with the real contract (`05b0fb3`).
- Acceptance-script bugs in run 1 (not app defects; 25/27): `getByText("Default")` substring-matched "Set as default", and one step read the recorded write before Playwright's `requestfinished` fired. Fixed; the 27/27 result is from a full re-run with a fresh account. The mocked spec's matcher was tightened the same way.

### Verification (this phase)

| Command | Result |
|---|---|
| `npm run lint` | 0 errors, 4 warnings (the known `<img>` warnings) |
| `npm run typecheck` | clean |
| `npm run test` | **1943/1943** (217 files) |
| `npm run build` | pass (`/account/addresses` prerendered) |
| `npm run test:e2e` | **76/76** (66 + 10 new) on three consecutive runs |

### Remaining gaps

- `ADDRESS_LIMIT_REACHED` and cross-user `404` were not provoked at runtime (see above).
- `DefaultAddressSelector` and `addressDefaultOptimistic` remain unmounted (checkout may use the selector).
- Checkout (`DeliveryMethodSelector`) still reads only `displayLines`/`isDefault`; it is integrated in FVS-026.

---

## Phase 5A closure: 2026-11-10 (admin, VERSION_CONFLICT, mounted logout, hydration)

| Item | Value |
|---|---|
| Frontend commits tested | `80b8db6` (mounted logout, defect 7) + `838e160` (reset-password hydration, defect 6), on top of `3ea70b3`. This document is updated in the commit after them |
| Backend | `C:\My projects\Bekaa3D-backend`, branch `main`, commit **`2dfb27b`** (unchanged) |
| Runtime | same as the run below: Docker Compose api/worker/postgres/redis/clamav `healthy`, `npm run dev` on :3000 proxying to :8000, dev media server on :8001 |
| Method | real Edge browser through Playwright against the real frontend and backend. **No route mocking.** Temporary scripts kept outside the repo (session scratchpad), never committed |
| Admin credentials | read only from `%USERPROFILE%\.bekaa3d\dev-admin.json` (`admin_email`, `admin_password`, `admin_totp_secret`; the schema the earlier admin runner already used). The file was missing. It was created by running the backend's own `scripts/dev_seed.py --rotate-credentials` and piping its one-time output straight into a local parser that wrote only those three keys. Nothing was printed, logged or committed. Rotation also **retired the previously exposed seed credentials**. The new recovery codes and seed-customer password were discarded unseen. Local development database only: never reuse for staging/production |
| Customer identities | fresh throwaway `accept-<timestamp>@example.com` accounts made through the real register flow. Tokens read from that account's dev-DB `email_outbox` row only |
| Disposable admin data | `acceptance-physical-<ts>` / `acceptance-stl-<ts>` products (deleted at the end), `Accept Category/Material/Colour <ts>` reference values (archived at the end). The `pickup_hours` and `accepting_orders` settings were changed and then restored. The throwaway customer was deactivated, then reactivated. No seeded record was modified |

**Overall: admin PASS (17/17 in one run) · real VERSION_CONFLICT PASS (API + UI) · mounted logout PASS (customer + admin) · reset-password hydration FIXED · mounted regression PASS (16/16 in one run).**

### Admin auth and authorization

| Check | Result | Evidence |
|---|---|---|
| Login → MFA challenge | **PASS** | `POST /auth/login` → `202` with keys `challenge_id, expires_in_seconds`; the UI showed "Verification code" |
| Real TOTP verification | **PASS** | code computed from the local secret, typed into the real form; `POST /auth/mfa/verify` → `204` (the contracted status) |
| Session established, `/me` role | **PASS** | `/me` `200`, `role === "admin"`; landed on `returnTo` `/admin/settings`; admin nav rendered |
| Customer on `/admin/*` (UI) | **PASS** | signed-in customer on `/admin/settings` got the normal not-found page; no admin nav |
| Customer on backend admin endpoint | **PASS** | `GET /admin/settings?limit=1` and `GET /admin/users` → `404 NOT_FOUND` (documented in BACKEND-RESPONSE.md: "a customer gets `404` from every admin path") |
| Admin write with wrong CSRF | **PASS** | `POST /admin/products` with a bad `X-CSRF-Token` → `403 CSRF_INVALID` |

### Admin screens

| Area | Result | Evidence |
|---|---|---|
| Settings: load | **PASS** | `GET /admin/settings` `200` |
| Settings: edit a safe setting | **PASS** | `pickup_hours` edited in the UI → `PATCH` `200` → "Saved"; value persisted across reload; original restored (`PATCH` `200`) |
| Settings: `accepting_orders` confirmation | **PASS** | Save opens "Change checkout availability"; **Cancel sends no PATCH**; "Confirm change" → `PATCH` `200`; flipped value persisted across reload; restored to `true` with the same dialog, confirmed by `GET /settings/public` |
| Customers: list, detail | **PASS** | `GET /admin/users` `200`; detail page for the throwaway customer |
| Customers: deactivate / reactivate | **PASS** | confirm dialog → `PATCH /admin/users/{id}` `200` → "Deactivated" (after reload, and `is_active=f` in the DB); reactivate → `200` → "Active" (reload + DB) |
| Categories / materials / colours | **PASS** (each) | create `201` (category with slug) → edit `200` → Disable `200` ("Disabled" persists across reload) → Enable `200` → Archive dialog → `DELETE` `204` → "Archived" after reload |
| Products: list | **PASS** | `GET /admin/products` `200`, real catalogue |
| Products: create physical (UI) | **PASS** | `201`, `type=physical`, lead time 3, batch 2, max qty 4, material/colour/dimensions set, `purchase_mode=online_only` |
| Products: create STL (UI) | **PASS** | choosing "STL (digital)" removes the physical section; `201`, `type=stl` with every physical field `null`; edit page shows the type locked ("Product type can't be changed after creation.", radios disabled) |
| Products: edit (UI) | **PASS** | name + batch size → `PATCH` `200` (version 1 → 2); both persisted across reload |
| Products: delete disposable (UI) | **PASS** | confirm dialog → `DELETE` `204` → back on `/admin/products`; public `GET /products/{slug}` `404`. Admin `GET` still answers `200` with `deleted_at` set (soft delete; observation 3) |
| Images: upload | **PASS** | two PNGs through the real file input → two `POST …/images` `201`; thumbnails loaded |
| Images: alt text / cover / reorder | **PASS** | "Save alt text" `PATCH` `200`; "Set as cover" `PUT …/cover` `200`; "Move up" `PUT …/images/order` `200`; order, cover and alt text all confirmed persisted by a fresh `GET` |
| Images: delete | **PASS, with a defect** | confirm dialog → `DELETE` `204`; one image left after reload; the remaining image is served through `/media` (`200`). **The "Delete image" dialog stays open after the delete succeeds** (defect 10) |

### Real `409 VERSION_CONFLICT`

| Check | Result | Evidence |
|---|---|---|
| Backend | **PASS** | `GET` product at v1 → `PATCH` with v1 `200` (v2) → `PATCH` with stale v1 → **`409 code=VERSION_CONFLICT`**; the stale write was not applied |
| Frontend: no silent retry | **PASS** | exactly **one** `PATCH` (the 409) from the edit form; none in the following 3 s |
| Frontend: authoritative re-fetch | **PASS** | a `GET /admin/products/{id}` is issued after the 409 |
| Frontend: form reconciles to server state | **PASS** | the Name field, which held the stale local edit, now shows the server's value |
| Frontend: safe banner | **PASS** | "This product was changed by someone else. Review the latest version below and try again." No raw `detail`, `request_id` or problem `type` on the page |
| Frontend: explicit resubmit | **PASS** | the admin edits and clicks Save changes again → `PATCH` `200` with the fresh version |

### Mounted logout (defect 7, closes the earlier "API level only" gap)

| Check | Result | Evidence |
|---|---|---|
| Control visible to a signed-in user | **PASS** | "Log out" button in the account nav (customer) and the admin nav (admin), one shared `LogoutButton` |
| Real logout | **PASS** | click → `POST /auth/logout` `204` → lands on plain `/login` (no `returnTo`); no raw backend error text |
| Frontend session state cleared | **PASS** | auth query set anonymous; user-scoped caches (`admin`, `notifications`) dropped (unit-tested) |
| Cookies | **PASS** | `access_token` and `refresh_token` removed from the browser. Pre-logout refresh cookie replayed in a fresh context → `POST /auth/refresh` `401 AUTH_REQUIRED` (session revoked) |
| `/me` after logout | **PASS** | `401 AUTH_REQUIRED` |
| Protected routes | **PASS** | `/account/profile` → `/login?returnTo=%2Faccount%2Fprofile`; `/admin/settings` → `/login` |
| Login afterwards | **PASS** | customer login `200`, `/me` `200` |
| Replayed pre-logout **access** cookie | observation 1 | still accepted by `/me` (`200`) until it expires |

### Reset-password hydration (defect 6)

| Item | Detail |
|---|---|
| Reproduction | Edge against the dev server, `/reset-password#token=…`: SSR HTML contained the invalid-link alert and no form; the client rendered the form; React threw **"Hydration failed because the server rendered HTML didn't match the client"** |
| Root cause | the token exists only in the URL fragment, which never reaches the server. The page read `window.location.hash` in a `useState` initializer: `null` on the server (invalid-link branch), the token on the client's hydration render (form branch). FVS-002 BATCH 4 had already fixed the same cause on `/verify-email` |
| Fix (`838e160`) | token state starts `undefined` ("not read yet") on both sides and renders a neutral loading state. One client-only effect captures the token, removes the fragment and keeps the token in memory. A ref guard stops React Strict Mode's second effect run from re-reading the already-cleared fragment. No `suppressHydrationWarning` |
| Security behaviour | unchanged: token read from the fragment only, fragment removed immediately, token only in component memory, never stored or logged (a console scan for the token found none) |
| Real-runtime result | **PASS**: SSR HTML is the neutral state; 0 hydration errors; real reset `confirm` `204`; login with the new password `200` |
| Regression tests | `src/app/reset-password/page.test.tsx`: hydrates real `renderToString` server markup (made without a fragment, as the server sees it) and fails on any recoverable hydration error, with and without a token. Plus a Strict Mode test |

### Mounted-app regression pass (one run, 16/16)

`/`, `/shop`, `/shop/geometric-planter` (real products, `/media` images loaded) · register (real Turnstile test widget) `202` · verify-email `204` · login · profile · notifications list + mark read · customer admin guard (UI + API) · mounted logout (all rows above) · forgot-password `202` · reset-password `204`, no hydration error · login with the new password. Admin areas: the 17/17 admin run above. Rate-limited flows were not repeated beyond one attempt each, and no `429` was provoked on purpose.

### New defect and observations from this run

10. **Image delete dialog stays open after a successful delete** (open, frontend, `src/components/admin/ImageGallery.tsx`). `onConfirm` calls `onDelete` but never clears `deleteTargetId`. The image is deleted (`204`), but the dialog stays up, and a second "Delete" click would target an id that no longer exists. Not one of this phase's two fixes, so it is left for a follow-up. The reference-data Archive dialog does not have this problem.
- Observation 1 (backend): logout revokes the session and clears cookies, but a **copied** pre-logout `access_token` stays valid until its 15-minute lifetime ends (stateless JWT, per VS-003). The browser no longer holds it, so this matters only if the cookie was exfiltrated. Confirm this is the intended trade-off.
- Observation 2 (backend, harness only): the outbox worker replaces sent payloads with `[redacted]`. Acceptance scripts must read the dev-DB token immediately after the request. One regression run lost that race and was re-run; the results above are from the re-run.
- Observation 3 (backend): after `DELETE /admin/products/{id}` → `204`, admin `GET` of that id still answers `200` with `deleted_at` set, while the public slug answers `404`. Consistent with soft delete; noted in case the admin UI should treat it as gone.
- Mocked E2E: the first `npm run test:e2e` run had 1 failure, "the readiness banner, whatever it shows, never breaks the shell". It counts `role=status` regions, then checks each one, and the home page's loading skeleton vanished between the two steps, because the dev server is wired to the real (fast) backend. It passed 5/5 on repeat, and the full suite then passed **66/66**. This is a pre-existing count-then-iterate race on `/`, which none of this phase's code touches.

### Verification (this phase)

| Command | Result |
|---|---|
| `npm run lint` | 0 errors, 4 warnings (the known `<img>` warnings) |
| `npm run typecheck` | clean |
| `npm run test` | **1870/1870** (1858 + 12 new) |
| `npm run build` | pass |
| `npm run test:e2e` | **66/66** (after one flaky first run, see above) |

### Remaining gaps

- Defect 10 (image delete dialog) is open.
- `503` captcha-unavailable is still unit-tested only.
- Observations 1 and 3 need a backend decision. Earlier observations 8 (`commit: "unknown"`) and 9 (login before email verification) are still open.
- Out of Phase 5A scope by instruction: addresses, cart, checkout, orders.

---

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

**Overall: public PASS · media PASS · auth PASS · account PASS · CSRF PASS · admin NOT RUN (blocked on credentials) · VERSION_CONFLICT NOT RUN (admin-only).** Admin and VERSION_CONFLICT were run and passed in the closure section above.

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
| Logout | **PASS (API level)** | `POST /auth/logout` with the frontend CSRF contract → `204`; `/me` then `401`; `/account/profile` redirects to `/login`. **No mounted UI control calls logout** (defect 7). Superseded: mounted logout PASS in the closure section |
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
| `409 VERSION_CONFLICT` | **NOT RUN** (then; **PASS** in the closure section) | in the current OpenAPI it exists only on admin products (`POST`/`PATCH`/`DELETE /admin/products…`); needs the admin session |

### Admin

| Feature | Result |
|---|---|
| MFA login, settings, customers, categories/materials/colours, product list/detail/edit, product create/update/delete, image upload/alt/cover/order/delete, admin CSRF, `409 VERSION_CONFLICT` (API and edit UI) | **NOT RUN: blocked on credentials.** The dev seed credentials are treated as compromised and must not enter source, tests, docs, `.env.local` or logs. A ready script reads them from a local file outside any repo (`%USERPROFILE%\.bekaa3d\dev-admin.json`: `admin_email`, `admin_password`, `admin_totp_secret`), types them only into the real login form, and never prints them. The file was not present when the run was attempted. **Resolved and run in the closure section above** |

### Integration defects found

1. **Captcha missing on three mounted auth flows** (register, resend, reset request): every real submit was `422`. **Fixed**; real runtime now `202`.
2. **`PublicSettingsRead` type drift** (removed `free_shipping_threshold`; missing `cash_payment_enabled`, `cash_max_order_total`). **Fixed.**
3. **`NotificationType` lacked `custom_request`**: generic fallback label only. **Fixed**; real notification renders "Custom request".
4. **No `/media` in local dev.** **Fixed** with the dev-only `MEDIA_PROXY_TARGET` rewrite.
5. **Mocked E2E race:** two login tests asserted `/account$` while `/account` server-redirects to `/account/profile`. They failed on the pre-change baseline too. **Fixed** (test-only).
6. **Hydration mismatch on `/reset-password`** (**fixed in `838e160`**, see the closure section; was open, frontend): the server renders the invalid-link alert because the token exists only in the URL fragment, and the client renders the form. React recovers on the client and the flow works, but it logs a hydration error. Not contract drift, so not changed in this phase.
7. **No logout control in the mounted UI** (**fixed in `80b8db6`**, see the closure section; was open, frontend): `AuthProvider.logout()` exists but nothing calls it. Not contract drift, so not changed in this phase.
8. Observation (backend): `/health/ready` reports `commit: "unknown"`.
9. Observation (backend): login succeeded for an account before its email was verified. Confirm with the backend team that this is intended.

### Environment notes

1. Partway through, Claude Code stopped the dev and media servers because the machine was critically low on memory. They were restarted after the user said to continue.
2. After that reclaim, the surviving orphan dev server's render workers were gone (`Jest worker encountered 2 child process exceptions`), so dynamic `/shop/[slug]` returned 500. A fresh dev server fixed it, and product detail passed on that server. This was not a code defect.
3. Acceptance scripts were kept outside the repo, in the session scratchpad. Script bugs found during the run (outbox template names; a cookie re-add that dropped the `/api/v1/auth`-scoped refresh cookie; an early URL-sanitization assertion) were fixed and the affected items re-run. The results above are from the fixed runs.

---

## Earlier attempt: 2026-10-19 (blocked)

Frontend `53b1ef3`, no backend checkout and no Docker on the machine, so the real-runtime portion was not attempted. That blocker is gone (see above).
