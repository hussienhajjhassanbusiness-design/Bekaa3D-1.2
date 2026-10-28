# ADR-046: Customer data export - six data sets from one read-only snapshot, composed in the reporting context, streamed, 3 a day, audited before the first byte (VS-044)

**Status:** Accepted (2026-10-28, VS-044).
**Date:** 2026-10-28
**Source basis:** [VS-044 slice](../vertical-slice-plan.md#vs-044--customer-data-export); owner answers to plan questions Q1-Q9 of 2026-10-28 (Q1 changed by the owner, Q2-Q9 as recommended); SRS §14.5, BR-124, F-034; FR-03; api-endpoints §9.1; [ADR-041](ADR-041-receipt-confirmation-and-problem-report.md) (Consequences); [ADR-045](ADR-045-business-analytics.md) d4, d5; [ADR-033](ADR-033-customer-order-read-model.md); [ADR-019](ADR-019-manual-stl-delivery.md).
**Confirms:** ADR-041's consequence "VS-044 (data export) … must include the contact messages that carry `user_id`" (decision 1).
**Amends:** SRS §14.5 and FR-03 (five data sets become six), and api-endpoints §9.1 (the row and the `DataExportRead` schema). Makes this one GET an exception to the "GET never needs CSRF" convention (d11).
**Applies first to:** `GET /api/v1/me/export`; no migration, the alembic head stays `eeed201dcfd2`.

## Context

SRS §14.5 and FR-03 listed five data sets (profile, addresses, orders with payment method and STL delivery records, reviews, offers). ADR-041 said the export must also carry the contact messages linked to the customer (problem reports). The SRS wins on a conflict, so the plan stopped and the owner decided. The export also reads five contexts at once, two of which (`payments.public` imports `ordering.public`; every context imports `identity.public`) cannot host the composition without an import cycle.

## Decision

1. **Six data sets (owner decision).** After the profile: `addresses`, `orders`, `reviews`, `offers`, `contact_messages`. A contact message is exported only when its `user_id` is the caller's, and only as `subject`, `message` and `created_at`: what the customer wrote. Its status is left out because no customer route shows it; its name, email, phone, order link, id and anything the administrator did are never exported. SRS §14.5 and FR-03 now list six sets.
2. **Customer-safe by construction.** Each record is a frozen dataclass in `reporting/domain/data_export.py`, and the API's `DataExportRead` is built from those same types, so the documented schema and the body cannot drift. A unit test fixes every field name. The records are the boundary: the offer and address ports return their domain rows and the adapters copy only the listed fields, while the order port uses VS-025's customer columns and the contact-message port selects only its three. Never exported: the password hash, phone hash, IP hashes, `admin_note`, provider references and metadata, redirect URLs, refund reasons and settlement fields, history reasons and actors, `delivered_by`, `recorded_by`, `remind_at`.
3. **Orders are the VS-025 projection (Q2).** Each order keeps what `OrderDetail` shows, without the action hints (`can_cancel`, `can_retry_payment`, `hold_expires_at`): `payment_method`, `payment_due` / `amount_due`, the shown payment attempt (provider, status and amount only), the customer's refunds (voided ones hidden, a failed-then-reissued one shown as its reissue, chargebacks never; VS-030 Q9), and a status history with `in_production` hidden. Failed earlier attempts are not listed.
4. **The STL delivery record (Q3)** is each STL line's `fulfillment_status` and `fulfilled_at` (when the administrator emailed the file), plus `delivery_email` (`customer_email_snapshot`, the address the files go to) on an order with a paid STL line: one `awaiting_delivery` or `delivered`, or one with `fulfilled_at` set (emailed, then refunded). An unpaid or cancelled STL line was never emailed, so its order has none (money review). `delivered_by` is never exported.
5. **Soft-deleted rows are exported and marked.** Addresses and reviews carry `deleted` and `deleted_at`. Orders, offers and contact messages are never soft-deleted.
6. **The composition lives in the reporting context (Q6).** As in ADR-045 d4, one port per data set and adapters that call only each context's `public` module. New export reads: `identity.public.addresses_for_export`, `ordering.public.orders_for_export` (a page of orders with lines and history batched), `negotiation.public.offers_for_export`, `engagement.public.contact_messages_for_export`; `engagement.public.reviews_for_export` (VS-036, with the WhatsApp-only badge mask) and `payments.public.order_payment_reader` / `customer_refunds` are reused.
7. **One snapshot, streamed (Q7).** Every port reads one `REPEATABLE READ, READ ONLY` transaction with ADR-045's 5 s statement timeout (`reporting.api.session.start_snapshot`). The handler reads the first data set before it returns, so a failed read is a clean `503 SERVICE_UNAVAILABLE` (or 500 for a bug) with no body. The body is then streamed: one chunk per page, the orders 50 at a time. A failure after the first byte cuts the body short, and the client sees invalid JSON.
8. **Audited before the first byte (Q4).** `user.data_exported` (actor and entity the caller, `request_id`, `ip_hash`, `after_data {"format_version": 1}`, no counts or content) is written in the request's unit of work after the first read and committed before the response is sent. No row is written if the first read fails, and no data leaves if the audit write fails.
9. **3 a day per user (Q5).** A fixed 24-hour window per user (`enforce_rate_limit`, key `data_export`), checked after the CSRF check (d11) and `current_verified_user`, so anonymous, unverified and forged callers spend none of it. An export that fails still counts. The `RateLimit-*` headers are copied onto the streamed response.
10. **Any verified account (Q9).** No role check: an administrator gets their own export. Anonymous is 401; unverified is 403 `EMAIL_VERIFICATION_REQUIRED`; a disabled or anonymised account is 401.
11. **CSRF on this GET (owner decision, closes the SRS review finding).** The session cookie is `SameSite=Lax`, so a cross-site link to the export would carry it and could spend a customer's three exports for the day. The route therefore runs the write routes' `require_csrf` before the rate limit: without this session's `X-CSRF-Token` header it is the same `403 CSRF_INVALID`, and nothing is counted or audited. The OpenAPI document lists `csrfToken` on this one GET (`_CSRF_READS` in `app/api/openapi.py`). A browser downloads it with `fetch` and the header, never with a plain link.

## Consequences

+ The body never shows more than the customer's own pages do, and a new field needs a deliberate change to the allowlist test.
+ The data sets agree with each other: an order, its payment and its refunds come from the same snapshot.
- A slow client holds a read-only connection for the length of the download; the 3-a-day limit bounds it.
- A failure part-way through returns a truncated body under a `200`, and it still costs one of the three exports.
- Closed, not accepted: a cross-site link could have spent a customer's three daily exports through the `SameSite=Lax` cookie (SRS review). d11 requires the CSRF header, so such a request is refused before the limit is counted.
- The frontend cannot offer the export as a plain `<a href>`: it must `fetch` with the header and save the blob.
- VS-045 must anonymise the same contact messages (by `user_id`).

## Alternatives rejected

- **Five data sets, replacing ADR-041's sentence** - the owner chose to export what the customer wrote.
- **Composing in Identity or Ordering** - import cycles through `identity.public` and `payments.public`.
- **Building the whole document before sending it** - the slice requires streaming, and a long order history would be held in memory.
- **Auditing after the stream ends** - the data would leave before its audit row exists.
