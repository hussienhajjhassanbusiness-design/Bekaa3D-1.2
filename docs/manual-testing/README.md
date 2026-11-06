# Manual testing guide

A hands-on guide for testing the Bekaa3D API by hand, through Swagger UI (`/docs`) on the
local Docker stack. Every endpoint, rule and error code in it was checked against the source
on the branch that added it. When the code and this guide disagree, the code wins: fix this
guide in the same PR as the code change.

[`docs/SRS.md`](../SRS.md) stays the specification. This guide describes what is **built**.

## Files

| File | What it covers |
| --- | --- |
| [00-overview.md](00-overview.md) | What Bekaa3D is, the business rules in plain language, the architecture and folder map, the main workflows as diagrams, running locally, seed accounts, Swagger login, reading emails |
| [01-identity.md](01-identity.md) | Register, verify, login, logout, refresh, password reset, admin MFA, profile, account deletion, address book, admin user management |
| [02-catalog.md](02-catalog.md) | Public storefront, search and suggestions, categories / materials / colours, admin products and product images |
| [03-ordering.md](03-ordering.md) | Cart, checkout (online and cash), orders, payment retry, cancellation, confirm receipt / report a problem, STL ownership, offer checkout, admin order release, cash blocks |
| [04-payments.md](04-payments.md) | Payment webhooks, admin payments (confirm, reconcile, record a late capture), refunds, chargebacks |
| [05-fulfillment.md](05-fulfillment.md) | Admin order list and detail, line transitions, cash handover, admin cancellation, the STL delivery queue |
| [06-negotiation.md](06-negotiation.md) | STL offers: submit, counter, accept, reject, withdraw, expiry |
| [07-engagement.md](07-engagement.md) | Notifications, wishlist, reviews and moderation, Bring Your Idea (custom requests), contact messages, engagement analytics |
| [08-platform-admin.md](08-platform-admin.md) | Settings, audit log, business analytics and data export (Reporting), health checks, the admin boundary |
| [99-test-checklist.md](99-test-checklist.md) | Every test from the files above as one ordered checklist |

## How each endpoint is written up

1. Method and path, who may call it (anonymous, customer, verified customer, administrator),
   and whether it needs `X-CSRF-Token` and `Idempotency-Key`.
2. What it does, and the business rules behind it (`BR-*`, `FR-*` from the SRS).
3. A request example and a response example.
4. The errors it can answer, with their `code` and when each happens.
5. Where the code is: router, application service, domain file.
6. Manual tests: one happy path and the important negative cases, each with its expected result.

Test IDs (`ID-01`, `CAT-03`, …) are stable and are the same in the per-context file and in the
checklist.
