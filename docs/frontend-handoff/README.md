# Frontend handoff pack

The backend's answer to the three frontend request files in [`../frontend-requests/`](../frontend-requests/).

| File | What it is |
|---|---|
| [`BACKEND-RESPONSE.md`](BACKEND-RESPONSE.md) | Every item of `BACKEND-UNLOCK-HANDOFF.md` answered by its ID, in the format of `BACKEND-RESPONSE-TEMPLATE.md` |
| [`openapi.json`](openapi.json) | The OpenAPI 3.1 document for everything that is built, generated from the code |
| [`../../scripts/dev_seed.py`](../../scripts/dev_seed.py) | The development seed: an administrator with MFA, a verified customer, a small catalogue |
| [`../../scripts/export_openapi.py`](../../scripts/export_openapi.py) | Regenerates `openapi.json` |

## Read this first

1. **Field lists are in `openapi.json`, not in the prose.** A response block names a schema; look it up under `components.schemas`.
2. **Two decisions removed parts of what you asked about.** ADR-019: the platform stores and serves no STL files, so there are no entitlements, library, downloads or asset uploads. ADR-024: the platform charges no shipping, so there are no shipping zones or free-shipping threshold. See [section 3 of the response](BACKEND-RESPONSE.md#3-removed-by-adr-019-and-adr-024).
3. **The backend is built up to the public catalogue.** Cart, checkout, payments, orders, refunds, addresses, contact and Bring Your Idea do not exist yet. Their answers are marked **provisional** in [section 4](BACKEND-RESPONSE.md#4-not-built-yet-provisional).
4. **Some items the request calls "confirmed" are not.** The list is in [section 6](BACKEND-RESPONSE.md#6-corrections-to-confirmed-items-in-the-request).

## Start the backend

From the repository root:

```sh
cp .env.example .env            # then replace every placeholder secret with one you generate
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose run --rm -T -e PYTHONPATH=src api python - < scripts/dev_seed.py
```

The last command prints the seed accounts' credentials **once**. Keep them in a password manager or your own git-ignored file. Details, the email workaround and the image-serving gap are in [A2](BACKEND-RESPONSE.md#domain--item-a2--local-backend-startup), [A3](BACKEND-RESPONSE.md#domain--item-a3--test-account-and-fixture-provisioning) and [B4](BACKEND-RESPONSE.md#domain--item-b4--imageasset-url-format).

## Status of every item

**Built**: answered from running code, with real examples. **Removed**: will never exist. **Not built**: provisional answer from the specification.

| ID | Item | Status | Backend slice |
|---|---|---|---|
| A1 | OpenAPI / schema source | Built | VS-005 |
| A2 | Local backend startup | Built | VS-001 |
| A3 | Test accounts and fixtures | Built (seed); file email adapter not built | — |
| B1 | Public settings | Built | VS-007 |
| B2 | Catalogue public list | Built | VS-015, VS-016 |
| B3 | Product detail | Built | VS-015 |
| B4 | Image URL format | Built; `/media` not served locally until VS-020 | VS-014 |
| B5 | Search suggestions | Built | VS-016 |
| C1 | Validation-error shape | Built | VS-001 |
| C2 | Cursor pagination | Built | VS-008 onward |
| C3 | Address book | Not built | VS-026 |
| C4 | Shipping zones | **Removed (ADR-024)** | — |
| C5 | Cart | Not built | VS-022 |
| C6 | Checkout | Not built | VS-023, VS-028 |
| C7 | Payment verification | Not built; parts undecided | VS-023 to VS-025 |
| C8 | Order status and actions | Not built | VS-023, VS-025, VS-029 |
| C9 | Entitlements / library | **Removed (ADR-019)** | — |
| C10 | STL download | **Removed (ADR-019)** | — |
| C11 | Ownership check | Product-level built; per-customer not built | VS-015; VS-023 |
| C12 | Idempotency-Key | Not built | VS-023 |
| P1-1 | Admin authorization source | Built | VS-005, VS-006 |
| P1-2 | Admin MFA | Built | VS-005 |
| P1-3 | Admin settings | Built | VS-007 |
| P1-4 | Admin customers | Built | VS-009 |
| P1-5 | Admin reference data | Built | VS-010 |
| P1-6 | Admin product CRUD | Built | VS-013 |
| P1-7 | Admin image upload | Built | VS-014 |
| P1-8 | Admin STL asset upload | **Removed (ADR-019)** | — |
| P1-9 | Admin entitlement grant | **Removed (ADR-019)** | — |
| P1-10 | Admin payments | Not built | VS-024 |
| P1-11 | Admin order fulfillment | Not built | VS-023b, VS-029 |
| P1-12 | Cancellation and returns | Not built | VS-031 |
| P1-13 | Refunds | Not built | VS-030 |
| P2-1 | Captcha provider | Not built; vendor undecided | VS-033 |
| P2-2 | Bring Your Idea | Not built | VS-034 |
| P2-3 | Contact form | Not built | VS-033 |
| P2-4 | Admin contact queue | Not built | VS-033 |
| P2-5 | Notifications | Built | VS-008 |
| P2-6 | Password reset | Built | VS-004 |
| P2-7 | Turnstile on register | Not built and not planned | — |
| P2-8 | Rate-limit shape | Built | VS-002 |

Totals: 20 built, 5 removed, 16 not built.

## Keeping this pack true

- `openapi.json` cannot go stale on `main`: `tests/unit/test_openapi_snapshot.py` fails until it is regenerated with `python scripts/export_openapi.py`.
- When a slice from section 4 is built, move its block to section 2, replace the provisional text with the real contract and a real example, and update the table above.
- The slice status table is at the top of [`../vertical-slice-plan.md`](../vertical-slice-plan.md).
