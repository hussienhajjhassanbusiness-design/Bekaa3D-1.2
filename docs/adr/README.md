# Bekaa3D Architecture Decision Records

**Recorded:** 2026-08-10

Only expensive-to-reverse decisions belong here. Folder names and small refactors do not.

## Index

- [ADR-001: Use PostgreSQL 16 as the primary database](ADR-001-use-postgresql-16.md)
- [ADR-002: Use UUID primary keys, time-ordered where available](ADR-002-uuid-primary-keys.md)
- [ADR-003: Keep V1 single-tenant](ADR-003-single-tenant-v1.md)
- [ADR-004: Use asynchronous I/O for API and persistence](ADR-004-async-io-stack.md)
- [ADR-005: Use Profile C Clean Architecture as a modular monolith](ADR-005-profile-c-modular-monolith.md)
- [ADR-006: Use secure cookie authentication, rotating refresh sessions, and admin MFA](ADR-006-cookie-authentication-and-mfa.md)
- [ADR-007: Version the REST API from day one and isolate admin routes](ADR-007-versioned-rest-api.md)
- [ADR-008: Represent money as integer cents with explicit currency](ADR-008-integer-cents-money.md)
- [ADR-009: Preserve business history with soft deletion and anonymisation](ADR-009-soft-delete-anonymisation-retention.md)
- [ADR-010: Use separate translation tables for bilingual content](ADR-010-translation-tables.md) — superseded by ADR-016
- [ADR-011: Use a transactional outbox and durable scheduled arq jobs](ADR-011-transactional-outbox-and-arq.md)
- [ADR-012: Use a payment-provider abstraction and independently verify payment](ADR-012-payment-provider-abstraction.md) — provider choice reopened by ADR-024
- [ADR-013: Centralize cross-context technical integrations behind shared ports](ADR-013-shared-external-integration-ports.md)
- [ADR-014: Use first-class entitlements and nginx-protected STL delivery](ADR-014-entitlements-and-protected-downloads.md) — superseded by ADR-019
- [ADR-015: Partition downloads and audit logs by month](ADR-015-partition-high-volume-logs.md) — downloads part superseded by ADR-019
- [ADR-016: Launch V1 English-only](ADR-016-english-only-v1.md)
- [ADR-017: Gate admin login on MFA rather than stepping up an existing session](ADR-017-login-gated-admin-mfa.md)
- [ADR-018: Store a per-user authentication epoch in PostgreSQL and check it on every authenticated request](ADR-018-authentication-epoch.md)
- [ADR-019: Deliver purchased STL files manually by email; the platform stores no STL files](ADR-019-manual-stl-delivery.md)
- [ADR-020: Use an optimistic `version` column for administrator edits](ADR-020-optimistic-versioning-for-admin-edits.md)
- [ADR-021: Scan the raw upload, then re-encode; store before the row commits](ADR-021-image-upload-pipeline.md)
- [ADR-022: Derive storefront commerce capabilities from product state only](ADR-022-storefront-commerce-capabilities.md)
- [ADR-023: Rank storefront search by relevance, fall back to trigram below five hits, and pin the mode in the cursor](ADR-023-storefront-search-order-and-fallback.md)
- [ADR-024: The courier prices and collects shipping; physical-only orders may be paid in cash on delivery](ADR-024-cash-on-delivery-and-courier-priced-shipping.md)
- [ADR-025: Admin order lines list their legal next actions; customers can check STL ownership; Turnstile captcha on five public forms](ADR-025-frontend-contract-decisions.md)
- [ADR-026: A refused captcha is `400 CAPTCHA_INVALID`, a Turnstile outage fails closed with `503`, and a coarse attempt limit runs before the captcha](ADR-026-captcha-refusal-and-outage.md)
- [ADR-027: Address book - required landmark notes, E.164 phones in a shared normaliser, a per-user write lock, and a first-address default](ADR-027-address-book-decisions.md)
- [ADR-028: Keyed, monthly-rotated IP hashes - a database salt plus an environment pepper, old salts deleted](ADR-028-keyed-monthly-rotated-ip-hashes.md)
- [ADR-029: Cart - hard-deleted lines, a type snapshot behind a composite FK, a first-add price snapshot, one cart lock and no product locks, a 50-line cap](ADR-029-cart-decisions.md)
- [ADR-030: Bring Your Idea submission - optional images under code-constant caps, a pre-parse attempt limit, private storage, expiry stamped at submission, and an admin notification category](ADR-030-bring-your-idea-submission.md)
- [ADR-031: Bring Your Idea pipeline - an API-streamed admin download until a server exists, a server-derived outcome, a bounded quote, and a cohort funnel](ADR-031-bring-your-idea-pipeline-and-api-streamed-download.md)

## Governance

- Do not rewrite accepted ADR history. A changed decision gets a new ADR that supersedes the old one.
- If a requirement changes, update the requirements/design first when applicable, then record the architecture consequence.
- Do not create ADRs for reversible implementation details.
