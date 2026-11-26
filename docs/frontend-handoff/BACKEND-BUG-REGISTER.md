# Backend Bug Register

> **DRAFT.** Not final until frontend editing and the final verification run are complete.

Date 2026-11-26. Backend `feat/homepage-hero-image` at `76f43f6`. Classifications and IDs follow
[API-CONTRACT-AUDIT.md](API-CONTRACT-AUDIT.md).

Only confirmed defects and open behaviour questions are listed here. Missing optional features are
**not** bugs and live in [BACKEND-FEATURE-REQUESTS.md](BACKEND-FEATURE-REQUESTS.md).

## Open

### BUG-01

| Field | Value |
|---|---|
| Title | A promotion can make products unbuyable: $0 effective price vs the zero-total checkout refusal |
| Classification | CONFIRMED BACKEND BUG (verified from source; not reproduced at runtime in this audit) |
| Priority | P2 |
| Introduced by | `ab34ff4` (seasonal promotions) |
| Affected frontend pages | Admin → Promotions (form); product detail; cart; checkout |
| Current endpoints | `POST/PATCH /api/v1/admin/promotions[/{id}]` (admin, MFA, CSRF); `POST /api/v1/checkout` (customer, CSRF) |
| Current contract | Promotions: `percentage` 1–100, `fixed` 1–100 000 000 cents; effective price `max(list − discount, 0)` (`catalog/domain/promotions.py`). Checkout: `422 PAYMENT_METHOD_NOT_ALLOWED`, `reason: zero_total` when the total is 0, online (`ordering/application/services/checkout.py:166`) and cash (`ordering/domain/cash.py:39`) |
| Expected | An administrator cannot save a promotion whose result is a product nobody can buy, or such a product can be bought |
| Actual | The promotion saves and shows "$0.00" on the storefront; every checkout containing only such lines is refused |
| Reproduction | 1. Admin creates an active `percentage` 100 promotion with scope `selected` on one product (or `fixed` ≥ its price). 2. As a verified customer, add that product to the cart. 3. `POST /checkout` (any method) → `422 PAYMENT_METHOD_NOT_ALLOWED`, `reason: zero_total` |
| Evidence | `promotions.py` `discounted_cents` (clamps to 0) and `validate_promotion` (allows 100); the checkout lines above; `docs/promotions.md` does not mention it. A $0 product was already possible (`ck_products_price_non_negative`), but promotions make it reachable with one admin action |
| Proposed change (a decision is needed; either option is valid) | **A.** Never produce 0: `percentage` 1–99, and clamp the effective price to at least 1 cent (or refuse a `fixed` value ≥ the price of any covered product at save time, with `422 VALIDATION_ERROR` on `discount_value`). **B.** Support zero-total orders: checkout creates a paid order with no payment attempt |
| Auth / CSRF | unchanged (admin + MFA + CSRF; customer + CSRF) |
| Validation | A: `discount_value` rule as above, named per field like the existing errors |
| Migration | A: **yes** if the `ck_promotions_percentage_range` CHECK changes to `<= 99`; none if only the clamp changes. B: no schema change expected, needs its own design |
| Backward compatibility | A: an existing 100 % promotion must be migrated or switched off; the frontend form's max (100) changes to 99. B: additive |
| Acceptance criteria | No storefront product shows an effective price the checkout refuses; a test covers 100 % and fixed ≥ price |
| Responsible | Backend (decision: product owner) |

### NV-01

| Field | Value |
|---|---|
| Title | A pending reissued refund cannot be voided once its line is `refunded` |
| Classification | NEEDS VERIFICATION (backend or product decision; currently intended by VS-030 U16) |
| Priority | P2 |
| Affected page | Admin → Refunds → refund detail (Void) |
| Endpoint | `POST /api/v1/admin/refunds/{refund_id}/void` (admin, MFA, CSRF, body `{reason}`) |
| Actual | `409 INVALID_STATE_TRANSITION`, `reason: line_already_refunded`, when the pending refund (with others) covers the whole line |
| Evidence | Real run 2026-11-11, order `B3D-WQMG40BW`. The rule is still present at `payments/domain/refunds.py:331/381`. Full write-up: `bekaa3D/docs/backend-handoff/REFUND-VOID-AFTER-REISSUE.md` |
| Question | Should voiding a never-paid refund reopen its line (restore the balance)? If not, what is the supported correction for a refund recorded by mistake? |
| Migration | no (logic only) |
| Acceptance | A documented answer, and either the rule changed with tests or the correction path documented |
| Responsible | Backend + product owner |

### NV-02

| Field | Value |
|---|---|
| Title | Worker heartbeat refreshes hourly; the compose comment implies every poll |
| Classification | NEEDS VERIFICATION |
| Priority | P3 |
| Evidence | `WorkerSettings` sets no `health_check_interval`, so arq's default of 3600 s applies. The heartbeat seen at runtime was 13 minutes old while the worker was busy. The compose comment says the check "reads the heartbeat the worker writes to Redis each poll" |
| Consequence | A frozen worker turns unhealthy only after up to about 1 h |
| Proposed | Decide a target detection time and set `health_check_interval` (for example 60 s) on `WorkerSettings`, or correct the comment |
| Migration | no |
| Responsible | Backend |

### NV-04

| Field | Value |
|---|---|
| Title | 13 failed jobs on the previous worker container, cause unknown |
| Classification | NEEDS VERIFICATION |
| Priority | P3 |
| Evidence | Heartbeat before recreation: `j_complete=4578 j_failed=13`. No error lines in that container's last 24 h of logs. The container was recreated on 2026-11-26, so its older logs are gone |
| Proposed | Watch `docker compose logs worker` for `failed`/`Traceback` during the final verification; no action if none recur |
| Responsible | Backend |

## Resolved during this handoff

| ID | Title | Root cause | Fix | Commit |
|---|---|---|---|---|
| RES-01 | Homepage hero image never appeared locally after a save | The frontend dev `/media` rewrite targets `http://localhost:8001`, which only a hand-started static server answered. Every `/media` URL returned 500 and the hero fell back to its default visual (product images were broken the same way) | Compose `media` service (api image, `python -m http.server`, read-only mount, `127.0.0.1:8001`); regression test `tests/unit/test_local_media_server.py` | `778a0bd` |
| RES-02 | Worker container always `unhealthy` while working | The probe `arq app.worker.WorkerSettings --check` imports the whole app. With `PYTHONDONTWRITEBYTECODE=1` and `./src` bind-mounted from Windows, that takes 16–31 s against a 10 s timeout | `app.worker_health` (arq `async_check_health`, same `REDIS_URL`, about 2 s); regression test `tests/unit/test_worker_health.py` | `76f43f6` |
| RES-03 | Two integration tests out of date after promotions | `test_cart_product_reader` pinned 1 query (now 1 product + 1 promotion query); `test_storefront_products` pinned the public field set (now `+ list_price, promotion`) | Tests updated with the contract | `ab34ff4` |
| RES-04 | 19 integration failures in the first full run (2026-11-24) | Test environment: `.env.example`'s placeholder `PHONE_HASH_SALT` overrode the test salt (production/staging startup checks), plus load timeouts (503) | Rerun with the test salt: all 21 previously failing tests pass. No code change | n/a |
