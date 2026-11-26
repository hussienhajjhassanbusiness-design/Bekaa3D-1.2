# Frontend → Backend Final Handoff

> **DRAFT.** This becomes final once frontend editing is finished and
> [FINAL-ACCEPTANCE-CHECKLIST.md](FINAL-ACCEPTANCE-CHECKLIST.md) is complete.

| | |
|---|---|
| Date | 2026-11-26 |
| Backend | `C:\My projects\Bekaa3D-backend`, `feat/homepage-hero-image` @ `76f43f6`, local and **not pushed**; `main` = `origin/main` = `7e52174` |
| Frontend | `C:\My projects\bekaa3D`, `master` @ `54cda03`, no remote configured |
| Contract | live `openapi.json` = committed snapshot, 153 operations |

## 1. Documents in this pack

| File | Use it for |
|---|---|
| [API-CONTRACT-AUDIT.md](API-CONTRACT-AUDIT.md) | every finding with its classification and priority; endpoint coverage |
| [BACKEND-BUG-REGISTER.md](BACKEND-BUG-REGISTER.md) | confirmed bugs, open behaviour questions, issues resolved during the handoff |
| [BACKEND-FEATURE-REQUESTS.md](BACKEND-FEATURE-REQUESTS.md) | contract changes, frontend integration gaps, optional ideas |
| [DATABASE-AND-INFRASTRUCTURE.md](DATABASE-AND-INFRASTRUCTURE.md) | migrations, compose, data safety, merge notes, production configuration |
| [FINAL-ACCEPTANCE-CHECKLIST.md](FINAL-ACCEPTANCE-CHECKLIST.md) | what must be run and ticked before submission |

The existing [README.md](README.md), [BACKEND-RESPONSE.md](BACKEND-RESPONSE.md) and
[openapi.json](openapi.json) are unchanged and still authoritative for field lists.

## 2. Backend changes made during frontend work, to preserve and merge

| Commit | Branch | What | Contract | Migration |
|---|---|---|---|---|
| `ab34ff4` feat: add seasonal promotions | `feat/promotions` | Admin-created price campaigns (percentage or fixed; all, physical, STL or selected products; no stacking). The effective price is computed once (`catalog/domain/promotions.py`) and read through `SqlCartProductReader`, so cart, checkout, order snapshot and offer ceiling all agree with the storefront. Contract: `docs/promotions.md` | **Added:** `GET/POST /admin/promotions`, `GET/PATCH /admin/promotions/{id}` (admin, MFA, CSRF on writes, audited), `GET /promotions` (public, rate limited). **Changed:** product reads' `price` is now the effective price; new `list_price` and `promotion`; new `promotion_id` filter on `GET /products` | `b7c41e2a9d10` |
| `4289c4a` feat: add admin-managed homepage hero image | `feat/homepage-hero-image` | Upload pipeline as for product images (10 MB, ClamAV fails closed, content-sniffed JPEG/PNG/WebP re-encoded, at least 400 px a side); the file is stored first, then the setting is updated and audited. Replaced files are reaped after 24 h. Contract: `docs/homepage-hero-image.md` | **Added:** `PUT /admin/home/hero-image` (multipart, admin, MFA, CSRF), `GET /home/hero-image` (public). **Changed:** generic `PATCH /admin/settings/homepage_hero_image` accepts only `null` | `c8e2f4a6b1d3` |
| `778a0bd` fix: serve public media in the local compose stack | same | Compose `media` service so `/media` works in local development (the bug: the hero and product images 500'd) | none | none |
| `76f43f6` fix: make the worker healthcheck answer within its timeout | same | `app.worker_health` probe replaces `arq … --check` in compose (the bug: the worker was always unhealthy) | none | none |

All four are additive for existing clients except `price` on product reads, which now carries the
promotional price while a promotion applies. That's intended: the list price moved to `list_price`.

## 3. Summary of findings

| Classification | Count | IDs |
|---|---|---|
| CONFIRMED BACKEND BUG | 1 | BUG-01 (P2) |
| MISSING BACKEND ENDPOINT | 0 | none |
| BACKEND CONTRACT CHANGE REQUIRED | 2 | CC-01 (P2), CC-02 (P3) |
| FRONTEND INTEGRATION REQUIRED | 8 | FE-01 (P1), FE-02 – FE-04 (P1), FE-05 – FE-06 (P2), FE-07 – FE-08 (P3) |
| CONFIGURATION REQUIRED | 6 | CFG-01 – CFG-06 (production) |
| NEEDS VERIFICATION | 4 | NV-01 (P2), NV-02 (P3), NV-03 (P1), NV-04 (P3) |
| OPTIONAL FEATURE | 5 | OPT-01 – OPT-05 |
| INTENTIONALLY UNSUPPORTED | 6 | see audit §5 |
| ALREADY IMPLEMENTED | 11 areas | see audit §4 |
| Resolved during handoff | 4 | RES-01 – RES-04 |

## 4. Known areas, one line each

| Area | Status | ID |
|---|---|---|
| Seasonal promotions | Implemented; limitations below | — |
| Promotion-aware price filter and sort | Contract change | CC-01 |
| Wishlist promotional price | Contract change | CC-02 |
| Zero-price promotional checkout | Bug | BUG-01 |
| Promotions pagination | Optional | OPT-01 |
| Category-based promotions | Optional | OPT-02 |
| Homepage hero image | Implemented | — |
| Public media serving | Local: resolved. Production: configuration | RES-01, CFG-02 |
| Worker health | Resolved; heartbeat interval to verify | RES-02, NV-02 |
| Manual payment provider | Backend done; frontend copy wrong | FE-01 |
| Product accepted payment methods, cart eligibility | Implemented | — |
| Admin-initiated offers | Optional (customer-submitted by design) | OPT-04 |
| Order-number search | Implemented (exact match) | — |
| Reviews and moderation | Backend done; no frontend UI | FE-02, FE-03 |
| Analytics | Backend done; no dashboard | FE-06 |
| Account export and deletion | Backend done; no frontend UI | FE-05, FE-04 |
| Notifications | Implemented | — |
| Production configuration | Email adapter missing; media, payments, captcha, secrets, ops | CFG-01 – CFG-06 |
| Refund void after reissue | Decision needed | NV-01 |

## 5. Recommended implementation order

1. **NV-03:** merge, then run the full backend suite once (the submission gate).
2. **FE-01:** manual provider outcome copy (frontend only, small, user-visible in V1 checkout).
3. **BUG-01:** pick option A or B; option A is a small validation change plus one migration.
4. **FE-04, FE-02, FE-03:** account deletion, reviews, moderation UI (backend done), as the
   submission scope requires.
5. **CC-01**, then **CC-02**: promotion-aware price filter, sort and wishlist.
6. **FE-05, FE-06:** export and analytics UI.
7. **NV-01, NV-02:** decisions and small follow-ups.
8. **CFG-01 – CFG-06:** before any production launch.
9. Optional items as time allows.

## 6. Ground rules kept during this work

- The frontend never computes prices, totals or payment state; the server is authoritative.
- No credentials appear in any document or commit; `.env` stays git-ignored.
- Nothing has been pushed.
