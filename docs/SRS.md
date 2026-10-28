# Bekaa3D — Software Requirements Specification

**Version:** 1.2
**Date:** August 2026; revised 2026-10-06, 2026-10-10
**Revision 1.1:** STL files are delivered manually by email and never stored on the platform — see ADR-019.
**Revision 1.2:** The courier prices and collects shipping; physical-only orders may be paid in cash on delivery; the online payment provider is an open decision — see ADR-024.
**Status:** Approved for development
**Supersedes:** Discovery Report v1 & v2, Design Pack Part 1 v1.0 & v1.1, Design Pack Part 2, Independent Audit

> This is the single authoritative document for Bekaa3D. It consolidates every
> decision, business rule, feature, workflow, and open item established during
> discovery, design, and audit. Where any earlier document conflicts with this
> one, **this document wins**.

---

## Table of Contents

**Part A — Business**

1. Project Overview
2. Actors & Roles
3. Business Rules Register
4. Feature Catalogue
5. Customer Journeys

**Part B — Functional Specification**
6. Catalogue & Search
7. Cart & Checkout
8. Orders & Fulfillment
9. Payments & Refunds
10. STL Delivery
11. Offers & Negotiation
12. Reviews, Wishlist & Engagement
13. Bring Your Idea & Contact
14. Identity & Accounts
15. Admin Dashboard
16. Notifications
17. Multilingual & SEO

**Part C — Technical Specification**
18. Architecture
19. Domain Model
20. State Machines
21. Database Schema
22. API Contract
23. Background Jobs
24. Infrastructure & Deployment

**Part D — Quality & Governance**
25. Non-Functional Requirements
26. Security Requirements
27. Testing Strategy
28. Build Phases
29. Risk Register
30. Open Decisions
31. Future Roadmap
32. Glossary

---

# PART A — BUSINESS

## 1. Project Overview

### 1.1 Purpose

Bekaa3D is a **dual-commerce platform** for a Lebanese 3D-printing business. It
serves two distinct commercial models through one system:

| Half                       | What it sells                       | How it transacts                                |
| -------------------------- | ----------------------------------- | ----------------------------------------------- |
| **A — Physical catalogue** | 3D-printed products, made on demand | Per product: checkout (paid online or in cash on delivery), WhatsApp, or both |
| **B — STL marketplace**    | Digital model files                 | Online checkout only, emailed by the administrator |

### 1.2 Business Context

The business operates in Lebanon, where commerce remains substantially
relationship-based and cash-oriented. The platform's defining design decision —
**per-product purchase mode** — exists to respect this: products can be sold
through a modern online checkout, through a human WhatsApp conversation, or
both, at the administrator's discretion per item.

This is also the system's accessibility safeguard. Customers without a wallet
balance or card are never locked out: they pay for physical goods in cash on
delivery or at pickup (ADR-024), or use WhatsApp.

### 1.3 Scope of Version 1

**In scope:**

* English-language public storefront with SEO
* Physical product catalogue with three purchase modes
* STL digital marketplace; purchased files are emailed manually by the administrator (ADR-019)
* Cart supporting mixed digital + physical orders
* Online payment through a provider still to be chosen (§30.4)
* Cash on delivery and cash at pickup for orders whose every line is physical (ADR-024)
* Manual fulfillment workflow (courier delivery and workshop pickup)
* Offer/negotiation system for STL products
* Reviews, wishlist, notifications
* Bring Your Idea lead workflow
* Admin dashboard with analytics
* Refunds with per-line partial support

**Explicitly out of scope for V1:**

* Product variants (colour/material selection at purchase) — routed to WhatsApp
* International shipping — routed to WhatsApp for quotation
* Courier API integration — fulfillment is manual
* Charging, zoning or refunding shipping — the courier prices and collects the delivery fee (ADR-024)
* Guest checkout — account required for all purchases
* Product comments (distinct from reviews) — deferred
* BYI online payment — lead workflow only
* STL licensing management
* Storing, hosting, or automatically delivering STL files — they stay on the administrator's own drive (ADR-019)
* Mobile applications
* Tax/VAT calculation

### 1.4 Success Criteria

1. A customer can discover, evaluate, and purchase an STL file, then receive it by email from the administrator.
2. A customer can order a physical product, pay online or in cash on delivery, and track it to delivery or pickup.
3. A customer can reach the business via WhatsApp for anything the platform doesn't transact.
4. The administrator can operate the entire business from the dashboard without database access.
5. The English storefront is fully usable end to end. V1 is English-only — see ADR-016.
6. No payment can be granted without independent server-side verification or, for cash, the administrator recording the cash collected.

---

## 2. Actors & Roles

### 2.1 Actor Catalogue

| Actor                        | Authenticated            | Capabilities                                                                                                                             |
| ---------------------------- | ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **Visitor**                  | No                       | Browse catalogue, view products/reviews, search, submit Bring Your Idea, submit contact message, initiate WhatsApp contact               |
| **Registered (unverified)**  | Yes                      | Everything a Visitor can do. **Cannot perform any write action.**                                                                        |
| **Customer (verified)**      | Yes                      | All purchasing, cart, checkout, offers, reviews, wishlist, order management, self-cancellation, data export, account deletion |
| **Administrator**            | Yes                      | Full catalogue, order, fulfillment, refund, offer, moderation, settings, and analytics control                                           |
| **System**                   | —                        | Scheduled jobs, projections, notifications, expiry, reconciliation                                                                       |
| **Payment Provider**         | External                 | Online payment processing, webhook callbacks, status queries. Provider not yet chosen (§30.4)                                            |
| **Courier**                  | External, outside system | Physical delivery; sets and collects the delivery fee, and collects the cash for cash-on-delivery orders. **Not a system user** — no tracking integration in V1 |

### 2.2 The Verification Boundary

**Browsing is open. Acting requires a verified email.**

| Action class                                      | Requirement                            |
| ------------------------------------------------- | -------------------------------------- |
| View catalogue, product, reviews, search          | None                                   |
| Register, resend verification, request a password reset, submit Bring Your Idea or the contact form | Captcha (Turnstile, ADR-025) + rate limit (guest permitted) |
| Cart, checkout, offer, review, wishlist           | Verified account                       |
| All admin functions                               | Admin role + (recommended) MFA         |

### 2.3 Future Roles

The role model is built extensibly from day one. V1 has a single administrator;
the architecture supports Super Admin, Manager, and Content Editor without
refactoring.

---

## 3. Business Rules Register

Every rule is numbered for traceability. `BR-` prefix.

### 3.1 Products

| ID     | Rule                                                                                                                        |
| ------ | --------------------------------------------------------------------------------------------------------------------------- |
| BR-001 | Each physical product has exactly one purchase mode: Online Only, WhatsApp Only, or Both.                                   |
| BR-002 | Purchase mode is changeable by the admin at any time.                                                                       |
| BR-003 | WhatsApp Only products bypass cart and checkout entirely.                                                                   |
| BR-004 | Purchase mode is re-validated at checkout; lines whose product changed mode are rejected.                                   |
| BR-005 | Physical products have no stock quantity — they are manufactured on demand.                                                 |
| BR-006 | Each physical product declares a production lead time in days.                                                              |
| BR-007 | Each physical product declares a maximum quantity per order line.                                                           |
| BR-008 | Each physical product declares a batch size (units producible per lead-time cycle).                                         |
| BR-009 | A product may be marked temporarily unavailable; its page stays live for SEO but add-to-cart is disabled.                   |
| BR-010 | Colour, material, and dimension variations are **not** selectable at purchase; customers requiring variations use WhatsApp. |
| BR-011 | Categories, materials, and colours are admin-managed controlled lists, never free text.                                     |
| BR-012 | Only main categories exist; no subcategories in V1.                                                                         |
| BR-013 | A category cannot be deleted while products are assigned to it; the admin must reassign first.                              |
| BR-014 | STL products are listed by the administrator only (single-vendor marketplace). The files themselves are never uploaded.      |
| BR-015 | An STL product may consist of several files; the administrator sends all of them together.                                  |
| BR-016 | Removed by ADR-019 — the platform keeps no STL files, so it keeps no file versions.                                         |
| BR-017 | Product name is required.                                                                                                   |
| BR-018 | Nothing is ever hard-deleted; all entities use soft delete.                                                                 |

### 3.2 Cart

| ID     | Rule                                                                                                           |
| ------ | -------------------------------------------------------------------------------------------------------------- |
| BR-020 | One cart per registered customer, persisting across sessions.                                                  |
| BR-021 | A cart may contain both STL and physical products simultaneously.                                              |
| BR-022 | A cart holds at most one line per product; adding an existing product merges quantities.                       |
| BR-023 | STL lines always have quantity exactly 1.                                                                      |
| BR-024 | Physical line quantity may not exceed the product's maximum per line.                                          |
| BR-025 | An STL the customer already owns (a paid, unrefunded STL line) cannot be added or purchased again.             |
| BR-026 | Cart lines snapshot the price at the time of adding; a changed price is surfaced for confirmation at checkout. |
| BR-027 | A delivery address is required only for a delivery order; the platform never charges a shipping fee (ADR-024). |

### 3.3 Checkout & Orders

| ID     | Rule                                                                                                                               |
| ------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| BR-030 | Checkout requires a verified account. There is no guest checkout.                                                                  |
| BR-031 | All prices and totals are recomputed server-side; client-supplied amounts are never trusted.                                       |
| BR-032 | Each order carries a human-readable order number.                                                                                  |
| BR-033 | Order lines snapshot product name, price, and image at purchase; later catalogue edits never alter order history. |
| BR-034 | An order's fulfillment method is Delivery, Pickup, or none (digital-only orders).                                                  |
| BR-035 | Order status is a derived projection of payment status and line statuses; it is never set directly.                                |
| BR-036 | Each order line carries its own fulfillment status.                                                                                |
| BR-037 | Estimated dispatch date = placement date + max across physical lines of (lead time × ceil(quantity ÷ batch size)); customers see it as the estimated ready date. |
| BR-038 | Customers are promised an estimated **dispatch** date, never a delivery date; courier transit and the delivery fee are outside the company's control. |
| BR-039 | Unpaid **online** checkouts expire after a configurable hold period and are cancelled automatically. Cash orders have no hold (BR-142). |
| BR-040 | The global "accepting orders" kill switch blocks new checkouts, cash orders included, and new offer submissions, but never affects payments already in flight, cash handovers of existing orders, or responding to, expiring or withdrawing an existing offer (ADR-034). |
| BR-041 | Checkout is idempotent; a repeated request with the same idempotency key returns the original order.                               |
| BR-042 | Digital lines enter `awaiting_delivery` on payment verification and are fulfilled when the administrator emails the file and marks the line delivered, independently of physical lines. |

### 3.4 Payments

| ID     | Rule                                                                                                                          |
| ------ | ----------------------------------------------------------------------------------------------------------------------------- |
| BR-050 | All prices are in USD.                                                                                                        |
| BR-051 | Money is stored as integer cents with an explicit currency code; floats are never used.                                       |
| BR-052 | Online payment goes through one or more providers behind a provider abstraction; which provider is an open decision (§30.4). A mock provider serves development and tests. |
| BR-053 | A payment callback is a notification, never proof of payment.                                                                 |
| BR-054 | Payment is confirmed only by independent server-side verification (status query or, failing that, manual admin confirmation). For a cash order, the administrator recording the cash collected at handover is that manual confirmation (BR-143). |
| BR-055 | The confirmed amount must match the amount due — the order total online, the sum of live line totals in cash; a lesser amount is never treated as paid. |
| BR-056 | Duplicate webhook deliveries are idempotent and never apply a payment twice.                                                  |
| BR-057 | No STL is sent before verified online payment. Physical production may start once an online order is paid or a cash order is placed. |
| BR-058 | At most one live payment attempt may exist per order; a retry of an online payment is permitted only after the prior attempt fails or expires. Cash orders have no payment attempts to retry. |
| BR-059 | No tax is applied in V1; the price shown is the price charged.                                                                |

### 3.5 Refunds & Cancellation

| ID     | Rule                                                                                                                             |
| ------ | -------------------------------------------------------------------------------------------------------------------------------- |
| BR-060 | STL purchases are final; this is presented and consent is recorded at checkout.                                                  |
| BR-061 | Physical orders are refundable at the administrator's discretion, on a published baseline policy.                                |
| BR-062 | Refunds may be partial and per-line, including part of a line; a line becomes refunded only when its whole line total is refunded. There is no shipping to refund (ADR-024). |
| BR-063 | Every refund creates a tracked obligation record that remains pending until settled. Every V1 refund is manual: the administrator pays it in the provider dashboard or in cash and settles it here. A failed refund stays owed until reissued. |
| BR-064 | A digital line covered in full by refunds or a chargeback is marked refunded; if it has not been sent yet it leaves the delivery queue and must not be sent. A partial refund leaves it in its state. |
| BR-065 | A file already emailed cannot be recalled; the protections are the all-sales-final consent record and the delivery record.     |
| BR-066 | A customer may cancel their own order while every live (not cancelled) physical line is still `pending`, whether it was paid online or is an unpaid cash order; lines an administrator already cancelled are ignored (owner decision 2026-10-19, ADR-033). |
| BR-067 | Once the administrator marks any line "start printing" (`in_production`), self-cancellation closes and cancellation becomes an admin decision. |
| BR-068 | STL lines are never self-cancellable.                                                                                            |
| BR-069 | A customer whose STL line was refunded may purchase the product again.                                                           |

### 3.6 Delivery & Fulfillment

| ID     | Rule                                                                           |
| ------ | ------------------------------------------------------------------------------ |
| BR-070 | Removed by ADR-024 — the courier prices delivery; there are no shipping zones. |
| BR-071 | Delivery addresses are Lebanese only in V1.                                    |
| BR-072 | International customers are directed to WhatsApp for a quotation.              |
| BR-073 | Workshop pickup is offered, is free, and requires no address; it is paid online or in cash at pickup under BR-141. |
| BR-074 | Removed by ADR-024 — there is no shipping fee or zone to snapshot.             |
| BR-075 | Fulfillment is entirely manual; no courier integration exists in V1.           |
| BR-076 | Removed by ADR-024 — there is no free-shipping threshold.                      |
| BR-077 | A returned item is not terminal; it may be re-shipped, reprinted, or refunded, or — for an unpaid cash line — cancelled with no refund. |
| BR-078 | Every physical order carries a contact phone: the address's phone for delivery, a phone entered at checkout for pickup. It is the courier's and administrator's contact. |

### 3.7 Offers

| ID     | Rule                                                                                                        |
| ------ | ----------------------------------------------------------------------------------------------------------- |
| BR-080 | Offers apply to STL products only, never physical products.                                                 |
| BR-081 | A customer may have only one live offer per STL product at a time.                                          |
| BR-082 | Counter-offers are unlimited in number.                                                                     |
| BR-083 | Each round resets an inactivity deadline for whoever's turn it is.                                          |
| BR-084 | An offer auto-expires if the party whose turn it is fails to respond in time.                               |
| BR-085 | Acceptance snapshots the agreed price, which is immutable thereafter.                                       |
| BR-086 | Acceptance issues a one-time checkout scoped to that customer and product, valid for a configurable window. |
| BR-087 | Once accepted, the inactivity timer is void; only the checkout window applies.                              |
| BR-088 | Acquiring the product by any other route automatically closes a live offer.                                 |
| BR-089 | Rejection starts a cooldown before the customer may open a new offer on that product.                       |
| BR-090 | Offers below a configurable percentage of list price are rejected at submission.                            |
| BR-091 | The complete negotiation history is preserved permanently.                                                  |
| BR-092 | A customer may withdraw their own pending offer.                                                            |

### 3.8 Reviews & Engagement

| ID     | Rule                                                                                      |
| ------ | ----------------------------------------------------------------------------------------- |
| BR-100 | Any verified user may review any product; a purchase is not required.                     |
| BR-101 | One review per user per product, editable but not stackable.                              |
| BR-102 | Reviews backed by a real purchase display a Verified Purchase badge: an owned STL line (paid, not refunded), or a physical line that was received (`delivered` / `picked_up`) and not refunded, returned or cancelled. A cash purchase counts only once its cash is recorded at handover. (Amended by ADR-044.) |
| BR-103 | WhatsApp-only products never show the badge, even if earlier platform purchases exist; the purchase data is kept. (Amended by ADR-044.) |
| BR-104 | The badge is recomputed from current line facts whenever a line changes state (paid, received, refunded, returned, cancelled). |
| BR-105 | Ratings are 1–5 integers.                                                                 |
| BR-106 | The administrator may hide or restore any review. Hide and restore are audited with an optional reason; a review its author deleted cannot be moderated (VS-037). |
| BR-107 | Reviews are rate-limited and filtered for links and profanity.                            |
| BR-108 | Wishlist is available to verified users; the admin sees totals and most-wishlisted items. |
| BR-109 | Product comments (separate from reviews) are not implemented in V1.                       |

### 3.9 Bring Your Idea & Contact

| ID     | Rule                                                                                     |
| ------ | ---------------------------------------------------------------------------------------- |
| BR-110 | Bring Your Idea accepts guest submissions, protected by captcha and rate limiting.       |
| BR-111 | Reference images are validated, re-encoded, scanned, and stored privately (admin-only).  |
| BR-112 | The workflow is a lead pipeline; it does not transact.                                   |
| BR-113 | Statuses: New → Contacted → Quoted → In Progress → Completed → Closed, with a Lost exit. |
| BR-114 | The admin may record a quoted amount and won/lost outcome for funnel reporting.          |
| BR-115 | Reference images expire and are purged after a retention period.                         |
| BR-116 | The contact form follows the same guest + captcha + rate-limit pattern.                  |

### 3.10 Accounts

| ID     | Rule                                                                                         |
| ------ | -------------------------------------------------------------------------------------------- |
| BR-120 | Registration requires email and password only; minimal friction.                             |
| BR-121 | Email verification is required before any write action.                                      |
| BR-122 | Accounts never verified are purged after a configurable period.                              |
| BR-123 | Customers may save multiple delivery addresses.                                              |
| BR-124 | Customers may export their data as JSON.                                                     |
| BR-125 | Account deletion anonymises rather than purges; financial and delivery records are retained. |
| BR-126 | Deletion is blocked while orders are open or refunds unsettled.                              |

### 3.11 Platform

| ID     | Rule                                                                                                |
| ------ | --------------------------------------------------------------------------------------------------- |
| BR-132 | Every admin action, auth event, payment, STL delivery, and status transition is audit-logged.       |
| BR-133 | Business parameters are admin-editable settings, not hardcoded constants.                           |
| BR-134 | All timestamps are stored in UTC.                                                                   |
| BR-135 | Removed by ADR-019 — there are no downloads to log.                                                 |

### 3.12 Cash Payment (ADR-024)

| ID     | Rule                                                                                                                                         |
| ------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| BR-140 | The customer chooses the payment method at checkout: online, or cash (on delivery, or at pickup). It is snapshotted on the order and never changes. |
| BR-141 | Cash is allowed only when every line of the order is physical. STL-only and mixed orders are paid online first, because an emailed file cannot be taken back. |
| BR-142 | A cash order is placed without payment and has no checkout hold; its physical lines may enter production once it is placed.                  |
| BR-143 | The administrator records the cash once per order, at handover, in the same action and transaction that marks every live line delivered or picked up. The order must have at least one live line, and the amount must equal the sum of live line totals and be above zero. A courier who later remits less is settled outside the platform. |
| BR-144 | A refused or unreachable cash delivery goes shipped → returned → cancelled; a refusal before shipping is cancelled from ready to ship; a pickup refusal or no-show is cancelled from ready for pickup — with no refund because nothing was paid. Admin cancels from these states record a reason: `refused`, `no_show` (pickup only) or `other`. When a cancel leaves the cash order with no live line, and every line cancelled from these states carries `refused` or `no_show` (at least one), cash is blocked for that customer and that contact phone until an administrator clears it. Refusing only some lines, or any `other`, never blocks. |
| BR-145 | Cash checkout is limited by admin-editable settings: on/off switch (`cash_payment_enabled`, default on), open unpaid cash orders per customer (`cash_max_open_orders`, default 1), and maximum cash order total (`cash_max_order_total`, default 10 000 cents = 100 USD). The open-order limit and the block match the customer or the normalised contact phone, and the total is checked after it is recomputed and must be above zero, with no line priced 0 ([ADR-043](adr/ADR-043-cancellation-and-returns.md) d12). A cash order the customer cancelled themselves counts as open for 24 hours ([ADR-038](adr/ADR-038-physical-checkout-and-cash-eligibility.md) d23). |
| BR-146 | The platform never charges, zones or refunds shipping. Checkout and emails say "delivery fee paid to the courier on delivery".               |
| BR-147 | After delivery or pickup the customer may confirm receipt or report a problem. Both are optional; the order completes without them.          |
| BR-148 | No physical work on an unpaid online order: every physical line transition requires a cash order or an online payment that reached paid (paid, partially refunded or refunded). The only exception is the system hold release cancelling an unpaid online order's pending lines. Unpaid online orders never appear in the fulfillment queue. |
| BR-149 | A paid line is a line of an order whose payment reached paid, unless it was cancelled without a refund obligation. A cancelled line of a cash order was never paid: nothing is refundable on it, and it earns no revenue and no Verified Purchase badge. A line cancelled by a chargeback is still a paid line; its chargeback nets it to 0 (ADR-045). |

---

## 4. Feature Catalogue

Complete inventory. `F-` prefix. Phase indicates build order (§28).

### 4.1 Public Storefront

| ID    | Feature                                                                                       | Phase |
| ----- | --------------------------------------------------------------------------------------------- | ----- |
| F-001 | Home page: hero, featured categories, why-choose-us, Bring Your Idea section, contact, footer | 1     |
| F-002 | Floating WhatsApp button, site-wide                                                           | 1     |
| F-003 | About Us: company story, services, contact information, gallery                               | 1     |
| F-004 | Physical product catalogue with pagination                                                    | 1     |
| F-005 | STL product catalogue with pagination                                                         | 1     |
| F-006 | Product detail page: gallery, description, specifications, reviews                            | 1     |
| F-007 | Full-text search over product names and descriptions                                          | 0     |
| F-008 | Faceted filters: category, material, colour, price range, rating                              | 0     |
| F-009 | Sorting: price, rating, newest                                                                | 0     |
| F-010 | Search autocomplete with typo tolerance                                                       | 1     |
| F-011 | WhatsApp click-to-chat with prefilled product context                                         | 1     |
| F-013 | SEO: slugs, meta tags, Open Graph, XML sitemap                                                | 0     |

### 4.2 Customer Account

| ID    | Feature                                          | Phase |
| ----- | ------------------------------------------------ | ----- |
| F-020 | Registration with email verification             | 0     |
| F-021 | Login / logout with rotating refresh tokens      | 0     |
| F-022 | Password reset                                   | 0     |
| F-023 | Resend verification email                        | 0     |
| F-024 | View account profile                              | 0     |
| F-025 | Saved address book with default selection        | 2     |
| F-026 | Order history and detail                         | 2     |
| F-027 | Purchased STLs with delivery status (in order history) | 3 |
| F-028 | Removed by ADR-019 (download history)            | —     |
| F-029 | Offer history                                    | 3     |
| F-030 | Wishlist management                              | 1     |
| F-031 | Review management                                | 1     |
| F-032 | Notification centre with read/unread             | 1     |
| F-033 | Self-service order cancellation (while every live physical line is pending) | 2 |
| F-034 | Data export (JSON)                               | 5     |
| F-035 | Account deletion via anonymisation               | 5     |

### 4.3 Commerce

| ID    | Feature                                                     | Phase |
| ----- | ----------------------------------------------------------- | ----- |
| F-040 | Mixed cart (digital + physical)                             | 2     |
| F-041 | Quantity management with per-product caps                   | 2     |
| F-042 | Price-change detection and confirmation at checkout         | 2     |
| F-043 | Removed by ADR-024 (shipping zone selection and fee)        | —     |
| F-044 | Workshop pickup option                                      | 2     |
| F-045 | Removed by ADR-024 (free-shipping threshold)                | —     |
| F-046 | Idempotent checkout                                         | 2     |
| F-047 | Online payment redirect and return handling                 | 4     |
| F-048 | Webhook receipt with signature verification where available | 4     |
| F-049 | Independent server-side payment verification                | 4     |
| F-050 | Payment reconciliation for missed callbacks                 | 4     |
| F-051 | Manual online-payment confirmation fallback                 | 4     |
| F-052 | Order confirmation with terms consent capture               | 2     |
| F-053 | Payment method choice at checkout: online, or cash on delivery / at pickup for physical-only orders, within the cash limits | 2 |
| F-054 | Record cash and mark delivered or picked up in one admin action | 2  |

### 4.4 Fulfillment

| ID    | Feature                                                             | Phase |
| ----- | ------------------------------------------------------------------- | ----- |
| F-060 | Order queue with status filters and search                          | 2     |
| F-061 | Per-line fulfillment status transitions                             | 2     |
| F-062 | Internal admin notes on orders                                      | 2     |
| F-063 | Delivery workflow: `pending` → `in_production` (internal) → `ready_to_ship` → `shipped` → `delivered` | 2 |
| F-064 | Pickup workflow: `pending` → `in_production` (internal) → `ready_for_pickup` → `picked_up` | 2 |
| F-065 | Return handling with re-ship, reprint, refund, or cancellation of an unpaid cash line | 2 |
| F-066 | Order cancellation by admin                                         | 2     |
| F-067 | Estimated dispatch (ready) date calculation                         | 2     |
| F-068 | Global accepting-orders kill switch                                 | 2     |
| F-069 | Customer receipt confirmation ("I got it") and problem report       | 2     |

### 4.5 Refunds

| ID    | Feature                                            | Phase |
| ----- | -------------------------------------------------- | ----- |
| F-070 | Full and partial per-line refunds                  | 2     |
| F-071 | Removed by ADR-024 (shipping fee refund)           | —     |
| F-072 | Refund obligation tracking until settled           | 2     |
| F-073 | Refunded STL line leaves the delivery queue        | 3     |
| F-074 | Pending refunds admin queue                        | 2     |

### 4.6 Digital Marketplace

F-080 to F-082 and F-084 to F-088 (STL upload, bundles, versions, downloads, download logging and statistics) are removed by ADR-019 and their IDs are not reused. F-083 is redefined from "entitlement grant on payment".

| ID    | Feature                                                         | Phase |
| ----- | --------------------------------------------------------------- | ----- |
| F-083 | Paid STL lines enter `awaiting_delivery` on payment verification | 3     |
| F-089 | Admin STL delivery queue; mark a line delivered (sent by email) | 3     |

### 4.7 Offers

| ID    | Feature                                     | Phase |
| ----- | ------------------------------------------- | ----- |
| F-090 | Offer submission with minimum floor         | 3     |
| F-091 | Admin accept / reject / counter             | 3     |
| F-092 | Customer accept / counter / withdraw        | 3     |
| F-093 | Inactivity expiry with turn-based deadlines | 3     |
| F-094 | One-time offer checkout at agreed price     | 3     |
| F-095 | Checkout window expiry                      | 3     |
| F-096 | Rejection cooldown                          | 3     |
| F-097 | Complete negotiation history                | 3     |
| F-098 | Auto-close on acquisition by another route  | 3     |

### 4.8 Engagement

| ID    | Feature                                               | Phase |
| ----- | ----------------------------------------------------- | ----- |
| F-100 | Reviews with ratings and Verified Purchase badge      | 1     |
| F-101 | Review moderation (hide/restore)                      | 1     |
| F-102 | Maintained rating aggregates                          | 1     |
| F-103 | Wishlist add/remove                                   | 1     |
| F-104 | Wishlist analytics for admin                          | 1     |
| F-105 | In-app notification centre                            | 1     |
| F-106 | Bring Your Idea submission with attachments           | 1     |
| F-107 | Bring Your Idea admin pipeline with quote and outcome | 1     |
| F-108 | Contact form and admin message queue                  | 1     |

### 4.9 Administration

| ID    | Feature                                     | Phase |
| ----- | ------------------------------------------- | ----- |
| F-110 | Product CRUD, both types                    | 0     |
| F-111 | Image upload, reorder, cover selection      | 0     |
| F-112 | Category, material, colour management       | 0     |
| F-113 | Removed by ADR-024 (shipping zone management) | —   |
| F-114 | Typed settings editor                       | 0     |
| F-116 | User management                             | 0     |
| F-117 | Audit log viewer                            | 5     |
| F-118 | Admin MFA                                   | 5     |

### 4.10 Analytics

| ID    | Feature                                                  | Phase |
| ----- | -------------------------------------------------------- | ----- |
| F-120 | Revenue by stream (physical vs STL), attributed per line; cash counted when recorded | 2 |
| F-121 | Recent purchases                                         | 2     |
| F-122 | Pending offers count                                     | 3     |
| F-123 | Wishlist statistics and most-wishlisted                  | 1     |
| F-124 | Best-selling STL (paid, unrefunded lines)                | 3     |
| F-125 | Top rated products                                       | 1     |
| F-126 | Customer statistics                                      | 2     |
| F-127 | Removed by ADR-019 (download statistics)                 | —     |
| F-128 | Bring Your Idea funnel conversion                        | 1     |

### 4.11 Platform Services

| ID    | Feature                                  | Phase |
| ----- | ---------------------------------------- | ----- |
| F-130 | Transactional email outbox with retry    | 0     |
| F-132 | Captcha on public forms                  | 5     |
| F-133 | Rate limiting on all sensitive endpoints | 5     |
| F-134 | Structured logging with correlation IDs  | 0     |
| F-135 | Audit logging                            | 0     |
| F-136 | Scheduled job infrastructure             | 0     |
| F-137 | Health and readiness endpoints           | 0     |
| F-138 | Backup with verification                 | 5     |

---

## 5. Customer Journeys

### 5.1 Purchase an STL File

1. Visitor searches or browses the STL catalogue.
2. Opens a product page: preview images, description, file information, reviews.
3. Registers and verifies email (required before any action).
4. Adds to cart, or submits an offer if negotiating.
5. Proceeds to checkout — no address required for a digital-only order.
6. Accepts terms including all-sales-final for digital goods.
7. Redirected to the online payment provider, completes payment.
8. System independently verifies the payment.
9. The STL line enters the admin's delivery queue; confirmation email and notification sent, saying the file will be emailed.
10. The administrator emails the file from their own drive to the customer's account email and marks the line delivered.
11. The customer is notified that the file has been sent. A lost file is re-sent on request, outside the system.

### 5.2 Purchase a Physical Product Online

1. Visitor browses the physical catalogue.
2. Opens a product configured Online Only or Both.
3. Sees price, production lead time, and estimated ready date.
4. Registers and verifies, adds to cart with quantity within the cap.
5. At checkout chooses delivery (with a saved address; "delivery fee paid to the courier on delivery") or free workshop pickup (with a contact phone), and chooses to pay online.
6. Server recomputes all totals; customer accepts terms.
7. Pays online; system verifies independently.
8. Order enters the admin queue.
9. Admin marks start printing (internal, not shown to the customer) → ready → shipped, or → ready for pickup.
10. Customer receives emails and notifications at ready ("your order is finished"), shipped or ready for pickup, and delivered or picked up.
11. Admin marks delivered or picked up; order completes. The customer may press "I got it" or "Report a problem" from the order page; neither is required.

### 5.3 Order via WhatsApp

1. Visitor opens a product configured WhatsApp Only or Both.
2. Taps Contact via WhatsApp; a prefilled message identifies the product.
3. All negotiation, pricing, payment, and delivery happen off-platform.
4. No order record is created; the business handles it manually.

### 5.4 Negotiate an STL Price

1. Verified customer submits an offer above the minimum floor.
2. Admin receives it in the offers queue.
3. Admin accepts, rejects, or counters. Unlimited rounds; each resets the deadline.
4. On acceptance the price is frozen and a one-time checkout is issued.
5. Customer pays within the checkout window.
6. The STL line enters the delivery queue (as in 5.1); the offer closes as paid.
7. If rejected, a cooldown must elapse before a new offer.

### 5.5 Request Custom Printing

1. Visitor (guest permitted) completes the Bring Your Idea form.
2. Uploads reference images; captcha and rate limits apply.
3. Request enters the admin pipeline as New.
4. Admin contacts the customer, records a quoted amount, marks Quoted.
5. All commercial agreement happens off-platform.
6. Admin advances to In Progress, Completed, Closed, or marks Lost.

### 5.6 Mixed Order with Partial Refund

1. Customer's cart contains one STL file and one physical product.
2. A single online payment covers both (a mixed order cannot be paid in cash); delivery address required for the physical line.
3. On verification: the STL line enters the delivery queue; the physical line stays `pending` and the admin marks start printing.
4. A printer failure makes the physical item unproducible.
5. Admin cancels that line and issues a partial refund covering it.
6. The STL line is unaffected; the administrator still sends (or has already sent) the file.
7. Order status becomes Partially Refunded; the refund is tracked until settled.

### 5.7 Purchase a Physical Product with Cash on Delivery

1. A verified customer's cart holds only physical products.
2. At checkout they choose delivery or pickup and pay in cash; the cash limits apply (BR-145).
3. The order is placed unpaid, with no checkout hold; confirmation email states the amount due in cash on delivery (or at pickup) and that the delivery fee is paid to the courier.
4. The administrator may call the contact phone, then marks start printing → ready → shipped (or ready for pickup), notifying the customer as in 5.2.
5. The courier delivers and collects the cash; the administrator records the cash and marks every line delivered in one action. The payment becomes paid and the order completes.
6. If the customer refuses the whole order or cannot be reached, its lines go shipped → returned → cancelled (reason `refused`) with no refund, and the customer and that phone number can no longer choose cash until an administrator clears the block. Refusing only some lines blocks nothing.

---

# PART B — FUNCTIONAL SPECIFICATION

## 6. Catalogue & Search

### 6.1 Product Attributes

**Common to both types:** name, description, category, price, multiple images, visibility flag, featured flag, availability toggle, SEO metadata (title, description, OG image, slug). Catalogue text lives in plain columns on the owning table — V1 is English-only, see ADR-016 and §17.2.

**Physical only:** purchase mode, material, colour, dimensions, production lead time (days), batch size, maximum quantity per line, weight (optional; unused since the courier prices delivery, ADR-024).

Availability is common to both types (owner decision, 2026-10-07): with manual STL delivery (ADR-019) the administrator must be able to pause STL sales.

**STL only:** no file attributes — the files stay on the administrator's drive (ADR-019). The description should say what the customer will receive.

**Derived:** average rating, review count.

### 6.2 Type Integrity

The database enforces that an STL product carries no physical-only fields and a physical product carries all required physical fields. This prevents, for example, an STL row acquiring a production lead time and corrupting the dispatch calculation.

### 6.3 Search

**Requirement:** full-text search with typo tolerance, over product names and descriptions.

Snowball stemming via the built-in `english` text-search configuration. Trigram indexes provide typo tolerance and power autocomplete.

Query strategy: full-text match first; fall back to trigram similarity when results are thin.

### 6.4 Filtering & Sorting

**Facets:** category, material, colour, price range, minimum rating, product type. Facets AND together and combine with search.

Because materials and colours are controlled reference lists rather than free text, facet values group correctly — free text would produce "PLA", "pla", and "PLA plastic" as three distinct filters.

**Sorts:** price ascending/descending, rating, newest.

**Pagination:** cursor-based for stable ordering under concurrent inserts.

### 6.5 Visibility

Storefront queries return only products that are non-deleted, visible, and belong to an active category. Unavailable products remain visible and indexable but cannot be added to cart — this preserves SEO value during a temporary stop-sell.

---

## 7. Cart & Checkout

### 7.1 Cart Behaviour

One persistent cart per customer. Adding a product already in the cart merges quantities rather than creating a second line — without this, a per-line quantity cap is trivially bypassed by adding the same product twice.

| Line type | Quantity            | Constraint                               |
| --------- | ------------------- | ---------------------------------------- |
| STL       | Always 1            | Rejected if already owned                |
| Physical  | 1..max_qty_per_line | Rejected if unavailable or WhatsApp-only |

### 7.2 Price Snapshots

Cart lines record the price when added. At checkout, current prices are compared; any change is surfaced to the customer for explicit confirmation before payment. This prevents both silent overcharging and stale-price disputes.

### 7.3 Checkout Validation Sequence

Executed inside a single transaction:

1. Verify the idempotency key; return the prior response if this is a replay.
2. Check the global kill switch — if orders are paused, reject with 503.
3. Lock the cart.
4. Validate every line: product exists, not deleted, visible, available, purchase mode permits online sale.
5. Re-verify STL ownership (a paid, unrefunded STL line); silently drop anything acquired since adding.
6. Validate quantities against current caps.
7. Determine fulfillment method; require an address for delivery and a contact phone for pickup (BR-078).
8. **Recompute all totals server-side.** There is no shipping component.
9. Validate the payment method against the recomputed total: cash only if every line is physical, cash is enabled, neither the customer nor the normalised contact phone is blocked from cash, fewer than `cash_max_open_orders` unpaid, uncancelled cash orders, or cash orders the customer cancelled themselves in the last 24 hours (ADR-038 d23), exist for that customer or phone, no line is priced 0 (ADR-043 d12), and the total is above zero and within `cash_max_order_total` (BR-141, BR-145). An online order names its provider when more than one is configured (§30.4).
10. Create order and order items with snapshots; for an online order also create a pending payment with the chosen provider. A cash order gets no payment until the cash is recorded.
11. Compute the estimated dispatch date.
12. Clear the cart.
13. Record terms consent with timestamp, including the cash terms for a cash order.

### 7.4 Conditional Requirements

| Cart contents      | Address      | Contact phone   | Fulfillment method | Payment method  |
| ------------------ | ------------ | --------------- | ------------------ | --------------- |
| STL only           | Not required | Not required    | None (null)        | Online          |
| Physical, delivery | Required     | From address    | Delivery           | Online or cash  |
| Physical, pickup   | Not required | Entered         | Pickup             | Online or cash  |
| Mixed, delivery    | Required     | From address    | Delivery           | Online          |
| Mixed, pickup      | Not required | Entered         | Pickup             | Online          |

No row carries a shipping fee: the courier sets and collects it on delivery (ADR-024).

### 7.5 Idempotency

Checkout requires an `Idempotency-Key` header. A repeated key with a matching request body returns the stored response; a mismatched body returns 409. This is what prevents a double-clicked checkout from creating two orders and two payment attempts.

---

## 8. Orders & Fulfillment

### 8.1 Order Composition

An order carries: order number, customer, source (cart or offer), derived status, fulfillment method, payment method (online or cash), monetary breakdown (subtotal, tax=0, total, currency), address snapshot, contact phone snapshot, customer note, internal admin note, estimated dispatch date, and lifecycle timestamps.

Each line carries: product reference, type, name snapshot, image snapshot, unit price, quantity, line total, its own fulfillment status, lead time and batch size snapshots, and an optional offer reference.

### 8.2 Why Per-Line Status

A mixed order can have its physical half cancelled while the digital half still awaits delivery or has been sent. A single order-level status cannot express this. Per-line status is therefore mandatory, and the order header status is computed from the lines.

### 8.3 Delivery Workflow

`pending` (received) → `in_production` (start printing) → `ready_to_ship` (finished) → `shipped` → `delivered`

`in_production` is internal: the customer sees it as "Received" and gets no email or notification for it. The customer is emailed and notified at `ready_to_ship` ("your order is finished"), `shipped` and `delivered`.

Exits: cancellation while `pending` (customer or admin) or later before shipping (admin only; a paid line creates a refund obligation, an unpaid cash line does not). From `shipped`, a failed or refused delivery moves to `returned`, which may then be re-shipped, reprinted, refunded (paid line), or cancelled (unpaid cash line, no refund). From `delivered`, an upheld claim on a paid line moves to `refunded`.

### 8.4 Pickup Workflow

`pending` → `in_production` → `ready_for_pickup` → `picked_up`

An online order was paid before production. A cash order is paid at the counter: the administrator records the cash and marks the lines picked up in one action (§9.8). A customer who never collects is cancelled by the administrator from `ready_for_pickup`. The workshop address and hours are configurable settings displayed at checkout and in the ready-for-pickup notification.

### 8.5 The Cancellation Cutoff

"Start printing" (`pending → in_production`) is the boundary. Before it, the customer may self-cancel the order's physical lines. After it, cancellation requires admin action because material and machine time have been committed. The administrator marks it when work begins.

Both lock the `orders` row first and then the lines (§20.8), so exactly one wins — the race cannot leave the order in an ambiguous state, even when printing starts on a different line from the one the cancel checks last.

### 8.6 Dispatch Estimation

`dispatch_days = max over physical lines of (lead_time_days × ceil(quantity ÷ batch_size))`, counted from when the order is placed, for both payment methods. Customers see it as the estimated ready date.

Batch size matters: if one print takes six hours and four fit on the bed, ten units is three cycles, not ten. A naive `max(lead_time)` would systematically understate multi-unit orders — precisely the orders where a missed date causes the most damage.

### 8.7 Admin Capabilities

View and filter the queue, including a "cash due" filter for unpaid cash orders (unpaid online orders never appear: BR-148); inspect customer and order detail; transition line statuses of cash orders and paid online orders; record cash at handover (§9.8); add internal notes (never customer-visible); cancel lines or orders; issue refunds; view the pending-refund obligations queue; work the STL delivery queue (§10.2); list and clear cash payment blocks.

### 8.8 Receipt Confirmation and Problem Reports

The delivered and picked-up emails have "I got it" and "Report a problem" buttons. They only open the order page; the action itself is a signed-in request there, never a link that changes state, because email scanners follow links. "I got it" records `receipt_confirmed_at` on the delivered lines. "Report a problem" records `problem_reported_at` and creates a contact message linked to the order for the administrator. Neither changes a line's state, and the order completes without them.

### 8.9 What the Customer Sees

The customer sees `in_production` as `pending` ("Received"), and their status history omits `in_production` entries. Because the cutoff is invisible, the order exposes a derived `can_cancel` flag: true only when the order has at least one live (not cancelled) physical line, is a cash order or has a payment that reached `paid`, has status `in_progress` or `partially_refunded`, and every live physical line is `pending`; physical lines an administrator already cancelled are ignored. It is false for an STL-only order and for an unpaid online order.

---

## 9. Payments & Refunds

### 9.1 Provider Abstraction

All online payment interaction sits behind a provider interface: create payment, query status, verify webhook signature (where supported). It has no refund operation in V1: every refund is manual (§9.6, ADR-024). Which provider — Whish, a card gateway, or both — is an open decision (§30.4); a mock adapter enables full development and testing without credentials. Additional providers require no changes outside their adapter. Cash is not a provider adapter: it is recorded by the administrator (§9.8).

### 9.2 Verification — the Critical Path

**Governing rule: a callback is a notification, never proof.**

The webhook endpoint is public. If it were trusted, a forged callback would get STL files emailed and goods manufactured for free. The verification sequence is therefore:

1. **Receive and persist** the webhook event immediately. A unique constraint on (provider, event id) makes duplicate delivery harmless — this is the idempotency mechanism.
2. **Return 200 quickly.** Providers retry on timeout; slow processing multiplies deliveries.
3. **Verify the signature** if the provider offers one. Failure rejects and alerts.
4. **Independently query** the provider for transaction status, holding no database locks. The adapter is the one named on the payment row (`payments.provider`), never the URL; an event whose provider differs from its payment's provider is stored, ignored and alerted.
5. **Confirm the amount matches** the order total exactly. A lesser amount is never treated as paid.
6. **Apply the result** in a second transaction: mark paid, move STL lines to `awaiting_delivery`, leave physical lines `pending` and eligible for production, close any live offer, recompute the order projection, write audit and history, enqueue emails.

If the provider offers no status query, the event is queued for **manual admin confirmation** against the provider dashboard. Slower, but a forged callback still yields nothing. Manual confirmation of a live attempt on an uncancelled order applies it; manual confirmation of an attempt that is no longer live, or on a cancelled order, records a late capture instead. A manual confirmation whose amount or currency differs from the attempt is refused (422) and never recorded as a late capture: the administrator refunds that payment in the provider's dashboard (ADR-036).

**Late capture.** If verification or manual confirmation finds money captured for an attempt that is no longer live (`failed` or `expired`), for an order already cancelled, or for an amount that does not match the order total (the attempt is then marked `failed`), the capture is never applied to the order: the payment row records `late_captured_at` and stays not live, an automatic refund obligation for the captured amount is created (`kind = late_capture`, no refund items, no human requester, outside the order projection, at most one non-failed per payment), an alert is raised, and the order's lines are untouched. This covers a customer who pays after the hold was released, an under- or overpayment, and a second capture while a retry attempt is live. A duplicate success for an attempt already `paid` is a no-op, even if the order was cancelled since.

### 9.3 Missed Callbacks

A scheduled reconciliation job queries the provider for any online payment stuck in processing beyond a threshold. Without it, a lost callback leaves a customer charged with nothing delivered and no recovery path — the single worst failure mode in the system.

### 9.4 One Live Payment Per Order

A database constraint permits only one payment per order in any state other than failed or expired, so a paid or refunded order never gets a second. A retry requires the prior attempt to have failed or expired, which reconciliation and verification provide; it locks the order first and re-checks that the order is still `pending_payment` and not cancelled, so it cannot race the hold release onto a cancelled order. A cash order has no payment until its single cash payment is recorded, so it never has a second.

### 9.5 Refund Policy

| Product type | Policy                                                                                                                                                                          |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| STL          | All sales final. Consent recorded at checkout with timestamp.                                                                                                                   |
| Physical     | Admin discretion on a published baseline: full refund before production; damaged, wrong, or undelivered resolved by replacement or refund with evidence within a stated window. A cash order is refundable only after its cash is recorded. |

### 9.6 Refund Execution

**Every refund is manual in V1.** The platform never calls a provider refund API: the administrator records the refund here, pays it in the provider dashboard or in cash, then settles it here (create → pay → settle). Each refund carries a typed `kind`: `admin` (issued by the administrator), `cancellation` (created by a cancel) or `late_capture` (§9.2). A chargeback is its own record, not a refund kind (§9.7, [ADR-042](adr/ADR-042-refunds-voids-and-chargebacks.md)).

Refunds may cover any subset of paid lines (BR-149); there is no shipping component. A line's refundable amount is its line total minus its items in refunds that are not failed and minus failed refunds not yet reissued (whose amount is reserved for the reissue); a cancelled cash line has 0. A refund of part of a line leaves the line in its state; a line becomes `refunded` when its refunds cover its whole line total — so a goodwill refund on an STL line still awaiting delivery keeps it in the queue and keeps the ownership. **An unfinished physical line** (`pending`, `in_production`, `ready_to_ship`, `shipped`, `ready_for_pickup`) cannot be refunded down to 0: the request gives 422 `REFUND_REQUIRES_CANCELLATION`, and the administrator cancels the line instead (a `shipped` line is refunded from `returned` once it comes back). A cancel's refund is the line's remaining balance, and none is created when that is 0. Each refund records amount, currency, kind, reason, requester (none for `late_capture`), approver and settlement state. A fully refunded digital line becomes `refunded`; one not yet sent leaves the delivery queue.

**Failed refunds stay owed.** A refund is marked `failed` when the money did not reach the customer (a bounced transfer, a rejected dashboard refund). Lines keep their state; nothing is reverted. The failed refund stays in the obligations queue as owed until the administrator reissues it, which creates a new pending refund of the same kind, items and amount and records `reissued_at` on the failed one. A failed refund never counts toward `refunded` order or payment status, but an owed one keeps the order `partially_refunded`, so an order with money still owed never reads `completed`.

The record remains a **tracked pending obligation** until settled — exactly the kind of task that gets forgotten without a queue driving it. The obligations queue lists pending refunds and owed (failed, not reissued) refunds. A cash payment is refunded up to the cash recorded. A line's or payment's refundable amount always counts what owed refunds reserve, so a failed amount is paid again only through its reissue.

**Voiding closes an obligation unpaid.** A pending or owed refund created by mistake is `voided` by the administrator, with a reason, audited (ADR-042 d2). A settled refund is never voided, a voided one is never reissued, and a refund whose line is already `refunded` or `cancelled` cannot be voided: such a line has no balance left, so its money would be stranded. Recording a chargeback voids the payment's open refunds itself (§9.7).

### 9.7 Chargeback Handling

A confirmed reversal is recorded as a **chargeback**, its own record (ADR-042 d3), never in the obligations queue: the bank has already moved the money. It is recorded once per provider dispute reference, with a required `Idempotency-Key`, on online payments only.

- **Open refunds are absorbed.** Recording it voids every pending and owed refund on that payment; their items become the chargeback's first items, so no line's coverage changes. If the bank took less than those refunds, the rest stays owed as a new pending refund ("remainder after chargeback"). Total payout therefore never exceeds the money paid.
- **The administrator's items** split the rest of the charge across lines, within each line's balance, and must total exactly that rest or, if it is larger, everything still refundable on the payment; anything else is refused (422 `CHARGEBACK_ALLOCATION_INVALID`). A line they bring to 0 becomes `refunded` if it is delivered, picked up, returned or an STL line (one not yet sent leaves the delivery queue), or `cancelled`, with no refund, if it is an unfinished physical line (ADR-042 d4).
- **Excess.** Whatever the bank took beyond that is recorded as excess and alerted. Excess therefore exists only once nothing is left to refund on the payment, so it can never be refunded again; recovering it is outside the platform.
- **A late-captured attempt** paid no line: its chargeback names no items and absorbs the open `late_capture` refund the same way, leaving a remainder when partial. One in a currency other than USD is not compared: the whole charge is excess. No order or payment status changes.

The event is audited. A file already emailed cannot be recalled; the mitigations are the recorded consent and the delivery record as evidence.

### 9.8 Cash on Delivery and Cash at Pickup

Decided in ADR-024.

1. **Eligibility.** Cash is offered only when every line is physical, `cash_payment_enabled` is on, no uncleared cash payment block matches the customer or the normalised contact phone, fewer than `cash_max_open_orders` unpaid, uncancelled cash orders, or cash orders the customer cancelled themselves in the last 24 hours (ADR-038 d23), exist for that customer or that phone, no line is priced 0 (ADR-043 d12), and the **recomputed** total is above zero and at most `cash_max_order_total`. Phones are matched by a keyed hash of the normalised number (`orders.contact_phone_hash`; `PHONE_HASH_SALT`, never rotated). Checked at checkout under the cart lock, which serialises one customer's checkouts; the block and the open-order count are also read under a transaction-scoped advisory lock on the phone hash, which serialises checkouts from different accounts with the same phone (the checks that need no phone run before it, ADR-038).
2. **Placement.** The order is created without a payment row and without a checkout hold. Stale-checkout release, reconciliation and payment retry never apply to it. Its physical lines may enter production at once.
3. **Handover — one action, one transaction, once per order.** The order must have at least one live (non-cancelled) line, and every live line must be `shipped` (delivery) or `ready_for_pickup` (pickup). The administrator enters the cash collected, which must equal the sum of live line totals and be above zero. Under the lock order of §20.8, the action marks the lines `delivered` or `picked_up`, creates one `payments` row (provider `cash`, status `paid`, amount, recording administrator, `verified_at`), recomputes the order status, and writes history, audit, the in-app notification and the delivered / picked-up email with the cash receipt. A unique index allows one cash payment per order. If a refusal leaves only lines totalling 0, the administrator cancels them (reason `other`) instead of a handover.
4. **When to record.** When the courier reports the order delivered and paid, for the full amount the customer paid. A courier who remits less to the business is settled outside the platform.
5. **Partial acceptance.** A line the customer refused is cancelled first (`returned → cancelled`, reason `refused`); the amount due drops and the handover covers the rest. A partial refusal never blocks cash.
6. **Refusal and no-show.** A refused or unreachable delivery goes `shipped → returned → cancelled`; a refusal before shipping is cancelled from `ready_to_ship`; a pickup refusal or no-show is cancelled from `ready_for_pickup`. Each of these cancels records `refused`, `no_show` (from `ready_for_pickup` only) or `other`. No refund obligation is created. When a cancel leaves the order with no live line, and every line cancelled from those states carries `refused` or `no_show` (at least one), a cash payment block is inserted for the customer and the order's phone hash, in the same transaction and under the phone advisory lock; the outcome does not depend on the order in which lines were cancelled, and any `other` prevents it. The block stores only the phone hash, so nothing readable survives anonymisation. An administrator lists and clears blocks. Accepted risk: a customer may enter someone else's phone; the administrator calls before printing, the other person can still pay online, and the block can be cleared.
7. **Proof.** No external input can create a cash payment; recording it is the documented manual admin confirmation of BR-054.
8. **Paid lines.** After the handover, the delivered lines are paid lines. A cancelled line of the same order is not (BR-149): it has nothing refundable and counts toward neither revenue nor the badge.

---

## 10. STL Delivery

Decided in ADR-019, which supersedes the automated-download design of ADR-014.

### 10.1 No Files on the Platform

STL files are never uploaded to, stored on, or served by the platform. They stay on the administrator's own drive, and the administrator emails them to the customer after payment. The platform takes the order and the payment, and tells the administrator what to send, to whom, and what is still outstanding.

### 10.2 Delivery Workflow

1. Payment verification moves every STL line of the order to `awaiting_delivery`, in the same transaction.
2. The checkout records the customer's verified account email on the order (`customer_email_snapshot`); this is the address the file is sent to.
3. The admin **STL delivery queue** lists every line awaiting delivery, oldest first, with order number, product, customer and email.
4. The administrator emails the files as attachments from their own mailbox, then marks the line **delivered**, recording who marked it and when. The action is audited.
5. The customer receives an in-app notification and an email saying the file has been sent, so they know to look for it (including in spam).

Delivery is not instant. The storefront and checkout state how STLs are delivered and the expected delivery time (§30.2).

### 10.3 Ownership

A customer **owns** an STL when they hold a paid, unrefunded STL line for it, whether or not it has been sent yet. Ownership blocks a repeat purchase (BR-025) and earns the Verified Purchase badge. At most one owning line per (customer, product) is enforced by a database constraint, so two parallel checkouts cannot both buy the same STL.

### 10.4 Refunds and Chargebacks

An STL line becomes `refunded` once refunds (or a chargeback) cover its whole total; a partial refund leaves it awaiting delivery and owned. Once `refunded`, a line still awaiting delivery leaves the queue and must not be sent. If it was already sent, the file cannot be recalled; the protections are the all-sales-final consent recorded at checkout and the delivery record. A customer whose line was refunded may buy the product again.

### 10.5 Re-sending

A customer who lost the file asks through the contact form or WhatsApp, and the administrator sends it again. The platform records only the first delivery.

---

## 11. Offers & Negotiation

### 11.1 Scope

Offers apply exclusively to STL products. Physical products are not negotiable through the system; those conversations happen on WhatsApp.

### 11.2 Turn-Based Model

An offer always has a `turn` (admin or customer) and a `responds_by` deadline for that turn. Each counter switches the turn and resets the deadline. Failure to respond expires the offer — this is the backstop that prevents indefinitely open negotiations.

### 11.3 Acceptance

Acceptance freezes the agreed price permanently, even if the list price later changes. A one-time checkout is issued, scoped to that customer and product, valid for a configurable window.

**Timer precedence:** once accepted, the inactivity timer is void; only the checkout window applies. Collapsing the two would expire an offer the customer is actively paying for.

### 11.4 Concurrency Safeguards

A database constraint permits one live offer per (customer, product) across the awaiting and accepted states — an application check loses this race under concurrent submissions.

If the customer acquires the product by any other route, any live offer auto-closes. This prevents both a double charge and an orphaned offer.

### 11.5 Anti-Abuse

A minimum offer floor, expressed as a percentage of list price, is enforced at submission. Rejection starts a cooldown before a new offer on the same product; each subsequent rejection re-arms it. Offer submission is rate-limited.

### 11.6 History

Every round is an append-only record: sequence, actor, action, amount, message, timestamp. The complete negotiation history is preserved permanently and is visible to both parties.

---

## 12. Reviews, Wishlist & Engagement

### 12.1 Review Model

Any verified user may review any product without purchasing. This is a deliberate decision that accepts some fake-review risk in exchange for review volume, mitigated by guardrails rather than by gating.

**Guardrails:** one review per user per product (editable), Verified Purchase badge where a real paid, unrefunded purchase exists, admin hide/restore, rate limiting, link and profanity filtering.

The badge is **recomputed** from current line facts whenever a line changes state — a cached flag written once would leave a refunded buyer displaying credibility they no longer hold. A physical line counts once it is received (`delivered` / `picked_up`); a paid line still in production does not. A partial refund keeps the badge; a full refund, a return or a cancellation removes it. A cash purchase is paid when its cash is recorded at handover; an unpaid or refused cash line never earns the badge, even in an order whose other lines were paid (BR-149). (Amended by ADR-044.)

WhatsApp-only products never show the badge. A product switched to WhatsApp-only after online sales keeps its purchase data, but the badge is hidden on every read while it stays WhatsApp-only. This is a known and accepted bias. (Amended by ADR-044.)

### 12.2 Rating Aggregates

Average rating and review count are maintained aggregates on the product, recalculated on review creation, edit, deletion, and moderation. Computing them on demand across a growing table would not survive catalogue growth.

### 12.3 Wishlist

Verified users add and remove products. The admin sees total wishlist counts and most-wishlisted products, informing promotion decisions. Price-drop alerts are deferred to a future version.

### 12.4 Notifications

An in-app notification centre complements email. Types include offer updates, purchase confirmation, STL file sent, customer-visible order status changes (never "start printing"), and account events. Each carries a type, JSON payload, and read state.

---

## 13. Bring Your Idea & Contact

### 13.1 Purpose

Bring Your Idea is the primary lead channel for custom printing — the business's highest-value work. It is deliberately a **lead workflow, not a transaction**: custom jobs require conversation about feasibility, material, and dimensions, so an automated quote-and-pay flow would wrap a process that must happen by hand anyway.

### 13.2 Submission

Guest submission is permitted. Requiring registration would suppress exactly the casual enquiries this channel exists to capture.

**Fields:** name, email, phone, project title, description, preferred material, preferred colour, dimensions, reference images.

**Protections:** captcha, per-IP and per-email rate limiting, file type validation by content inspection (not extension), size and count caps, image re-encoding to strip embedded payloads, malware scanning, private storage.

### 13.3 Pipeline

`new` → `contacted` → `quoted` → `in_progress` → `completed` → `closed`, with a `lost` exit from contacted or quoted.

The admin records a **quoted amount** and **won/lost outcome**. These are admin-only and exist solely so the business can measure conversion on its main lead channel — without them, the funnel is invisible.

### 13.4 Attachment Retention

Reference images carry an expiry and are purged from both disk and database by a scheduled job.

### 13.5 Contact Form

Same guest-plus-captcha pattern. Messages enter an admin queue with statuses new, read, replied, archived.

---

## 14. Identity & Accounts

### 14.1 Registration

Email and password only. Every additional field costs conversion, and the account requirement already imposes friction.

### 14.2 Verification Gate

Registration creates an unverified account that may browse but perform **no write action**. This is the system's primary anti-abuse control and applies uniformly to cart, checkout, offer, review, and wishlist.

Consequence: email delivery is critical-path infrastructure. A verification email that does not arrive locks the user out of the entire product. This mandates a reputable transactional provider, correct SPF/DKIM, an outbox with retry, delivery monitoring, and a resend flow.

Accounts never verified are purged after a configurable period.

### 14.3 Authentication

Passwords hashed with Argon2id. Tokens delivered as httpOnly, Secure, SameSite cookies — not accessible to JavaScript, which eliminates token theft via XSS. Access tokens are short-lived; refresh tokens rotate on use and are stored hashed. CSRF protection applies to all unsafe methods.

### 14.4 Addresses

Multiple saved addresses with a default. Fields: label, recipient name, Lebanese phone number, governorate, city, area, street, and **landmark notes** — Lebanese addressing is landmark-based, so free-text notes are functionally required rather than decorative. The phone is the courier's contact for delivery and is snapshotted onto the order (BR-078).

### 14.5 Data Rights

**Export:** JSON containing profile, addresses, orders (with payment method and STL delivery records), reviews, offers, and the contact messages the customer sent while signed in (what they wrote only; ADR-046).

**Deletion:** implemented as anonymisation. Login is disabled and personal data stripped, but financial and delivery records are retained in anonymised form — required for accounting and referential integrity. Deletion is blocked while orders are open or refunds unsettled, since fulfilling an order requires the name and address.

---

## 15. Admin Dashboard

### 15.1 Catalogue Management

Product CRUD for both types; image upload, reorder, and cover selection; category, material, and colour management; visibility, featured, and availability toggles; SEO metadata; marking STL lines delivered.

### 15.2 Order Management

Filterable queue by status, date, customer, fulfillment method, payment method, and cash due; order detail with customer information and contact phone; per-line status transitions; cash handover recording; internal notes; cancellation; refund issuance.

### 15.3 Queues

STL lines awaiting delivery; cash orders awaiting handover; Bring Your Idea pipeline; contact messages (including problem reports linked to orders); pending offers; pending refund obligations; payments requiring manual confirmation; review moderation.

### 15.4 Settings

Typed, admin-editable configuration with audit trail. At minimum: accepting-orders kill switch, offer response window, offer checkout window, rejection cooldown, minimum offer percentage, checkout hold period, unverified purge period, cash payment switch, maximum open cash orders per customer, maximum cash order total, pickup address and hours, WhatsApp number.

These are settings rather than constants specifically so operational changes never require a deployment.

### 15.5 Analytics

**Revenue must be attributed per line item**, not per order — a mixed order would otherwise corrupt the STL revenue figure the business relies on. Revenue is paid line amounts minus refunds; there is no shipping revenue. Cash revenue counts from the moment the cash is recorded; an unpaid cash order, and a cancelled line of a paid cash order, is not revenue (BR-149). Each line, with its refunds and chargebacks, belongs to the `Asia/Beirut` day its payment was verified (for cash, the handover), so a later refund lowers that day; a chargeback is subtracted once, and its excess is reported apart. Exact definitions: api-endpoints §27.1 (ADR-045).

Reports: revenue by stream, recent purchases, customer statistics, top rated products, most wishlisted, best-selling STL, STL lines awaiting delivery, pending offers, Bring Your Idea funnel conversion.

There is no inventory dashboard, as products are made on demand.

---

## 16. Notifications

### 16.1 Email Catalogue

| Trigger                     | Recipient |
| --------------------------- | --------- |
| Registration verification   | Customer  |
| Verification resend         | Customer  |
| Password reset              | Customer  |
| Order confirmation (online, or "pay in cash on delivery / at pickup") | Customer |
| Payment receipt (online)    | Customer  |
| STL file sent               | Customer  |
| Order finished (ready)      | Customer  |
| Order shipped               | Customer  |
| Ready for pickup            | Customer  |
| Order delivered / picked up, with the cash receipt for a cash order and "I got it" / "Report a problem" buttons | Customer |
| Order cancelled (for a cash order with lines left, restating the new amount due) | Customer |
| Refund issued               | Customer  |
| Offer countered             | Customer  |
| Offer accepted              | Customer  |
| Offer rejected              | Customer  |
| Offer expiring soon         | Customer  |

WhatsApp-only orders generate no system email — those conversations happen entirely off-platform. "Start printing" sends nothing; it is internal. Every email about a delivery order says "delivery fee paid to the courier on delivery".

### 16.2 Delivery Architecture

Emails are written to an **outbox table inside the business transaction** and delivered afterwards by a worker. This guarantees that a transient email failure can never roll back a payment, and that a queued message is never silently lost. Retry uses exponential backoff with a failure alert threshold.

---

## 17. SEO

### 17.1 Coverage

English only, across navigation, static pages, product names and descriptions, categories, materials, colours, emails, error messages, and SEO metadata.

### 17.2 Storage Model

Product, category, material, and colour text lives in plain columns on their owning tables — no separate translation tables. This keeps slug uniqueness enforceable by a single index and keeps search indexing straightforward.

### 17.3 URL Strategy

Slugs are unique among non-deleted rows.

A soft-deleted product must release its slug, otherwise a deleted product holds its URL forever and the admin can never reuse it.

### 17.4 SEO Requirements

Meta title and description, Open Graph image, canonical URLs, an XML sitemap, and structured data for products and reviews.

# PART C — TECHNICAL SPECIFICATION

## 18. Architecture

### 18.1 Stack

| Layer                       | Technology                                    |
| --------------------------- | --------------------------------------------- |
| API                         | Python 3.13, FastAPI, Pydantic v2             |
| ORM                         | SQLAlchemy 2 (async), Alembic migrations      |
| Database                    | PostgreSQL 16                                 |
| Queue / cache / rate limits | Redis                                         |
| Worker                      | arq (jobs and cron)                           |
| Reverse proxy               | nginx (TLS, static, protected file streaming) |
| Scanning                    | ClamAV                                        |
| Containerisation            | Docker Compose                                |

### 18.2 Architectural Style

Clean Architecture with layered separation: **domain** (entities, invariants, pure logic), **application** (use cases, orchestration), **infrastructure** (repositories, external adapters), **api** (routers, schemas).

Dependencies point inward only. Domain has no framework or database imports.

### 18.3 Bounded Contexts

| Context        | Owns                                                                |
| -------------- | ------------------------------------------------------------------- |
| Identity       | Users, addresses, sessions, tokens                                  |
| Catalog        | Products, categories, materials, colours, images                    |
| Ordering       | Cart, orders, order items, status history, cash payment blocks      |
| Payments       | Payment attempts (online and recorded cash), webhook events, refunds |
| Fulfillment    | Fulfillment transitions, cash handover, STL delivery — no tables of its own since ADR-024; line state lives on order items |
| Negotiation    | Offers, offer rounds                                                |
| Engagement     | Reviews, wishlist, notifications, custom requests, contact messages |
| Platform       | Settings, audit log, email outbox, idempotency records              |
| Reporting      | No tables of its own (ADR-045); business analytics and the customer data export (ADR-046) read every other context through its public port |

Cross-context access goes through service interfaces. Direct joins into another context's tables are prohibited — that practice is what turns "Clean Architecture" into folder decoration.

### 18.4 Key Abstractions

| Abstraction              | Purpose                                               |
| ------------------------ | ----------------------------------------------------- |
| Payment provider port    | Online provider still to be chosen (§30.4), mock for development |
| Storage port             | Local filesystem today, S3-compatible later           |
| Email provider port      | Provider-agnostic transactional delivery              |
| Captcha port             | Provider-agnostic verification                        |
| Repository per aggregate | Persistence isolated from domain logic                |

---

## 19. Domain Model

### 19.1 Entity Inventory

**Identity:** User, Address, Session, VerificationToken, PasswordResetToken

**Catalog:** Product, ProductImage, Category, Material, Colour

**Ordering:** Cart, CartItem, Order, OrderItem, OrderStatusHistory, CashPaymentBlock

**Payments:** Payment, WebhookEvent, Refund, RefundItem

**Fulfillment:** none of its own (ShippingZone removed by ADR-024)

**Negotiation:** Offer, OfferRound

**Engagement:** Review, WishlistItem, Notification, CustomRequest, CustomRequestAttachment, ContactMessage

**Platform:** Setting, AuditLog, EmailOutbox, IdempotencyRecord

### 19.2 Core Invariants

Numbered for traceability. `INV-` prefix.

**Money**

* INV-01 — All monetary values are integer cents with an explicit currency code.
* INV-02 — Prices and totals are always recomputed server-side; no order carries a shipping amount.
* INV-03 — Order and line snapshots are immutable after placement.

**STL delivery**

* INV-04 — An STL is never sent before its payment is verified; only a line in `awaiting_delivery` can be marked delivered.
* INV-05 — STL lines enter `awaiting_delivery` atomically with payment verification.
* INV-06 — Marking a line delivered or refunded never deletes it; it sets a timestamp.

**Ordering**

* INV-07 — Lines whose product is WhatsApp-only, invisible, unavailable, or deleted are rejected at checkout.
* INV-08 — STL lines have quantity exactly 1 and are rejected when the customer already owns the STL (§10.3).
* INV-09 — A cart holds at most one line per product; merged quantity respects the cap.
* INV-10 — The kill switch blocks new checkouts and new offers but never in-flight payments or existing offers.
* INV-11 — Dispatch estimate accounts for quantity and batch size.

**Content**

* INV-12 — Product name is required.
* INV-13 — Slugs are unique among non-deleted rows.

**Security**

* INV-14 — Every write action requires a verified email.
* INV-15 — Every fetch by ID verifies ownership or admin role.
* INV-16 — STL files are never stored on or served by the platform.

**Consistency**

* INV-17 — Verified Purchase badges recompute from current line facts whenever a line changes state (ADR-044).
* INV-18 — At most one paid, unrefunded STL line per (customer, product); a refunded buyer may re-purchase.
* INV-19 — At most one live payment per order.
* INV-20 — Order status is a projection, never assigned directly.

**Cash payment**

* INV-21 — A cash order has only physical lines (enforced by the database through `payment_method` copied onto order items under a composite foreign key).
* INV-22 — A cash payment is created only by the handover action, in the same transaction that marks every live line delivered or picked up, for exactly the sum of live line totals and above zero; at most one per order (unique index).
* INV-23 — No physical line of an unpaid online order changes state, except the hold release cancelling its pending lines.
* INV-24 — Every write that changes an order's lines, payment or refunds locks the `orders` row before any line (§20.8).

---

## 20. State Machines

### 20.1 Payment

```
pending ──> processing ──> paid ──> partially_refunded ──> refunded
   │             │           └────────────────────────────> refunded
   │             ├──> failed
   └──> expired  └──> expired

refunded ──> partially_refunded ──> paid      (a refund failed or voided; ADR-042)
```

For an online payment, `paid` is reachable only through independent server-side verification of a live attempt on an uncancelled order. A success found for a `failed` or `expired` attempt, or on a cancelled order, is a late capture (§9.2): it sets `late_captured_at`, never changes the status to `paid`, and is refunded automatically. A cash payment is never `pending` or `processing`: it is created directly as `paid` by the handover action (§9.8), and may then be refunded like any other. "A payment that reached `paid`" means status `paid`, `partially_refunded` or `refunded`. That status is a projection of its refunds and chargebacks, recomputed with the order's: it moves back when a refund fails or is voided, and never changes on settlement.

### 20.2 Order Status (derived projection)

```
online order, no payment reached paid:
    order cancelled by hold release  → cancelled
    otherwise                        → pending_payment
cash order, no payment yet:
    all lines cancelled              → cancelled
    otherwise                        → in_progress
payment reached paid (online or cash):
    an owed refund                   → partially_refunded
    all lines cancelled              → cancelled
    refunds cover all paid money     → refunded
    any refund or chargeback         → partially_refunded
    all lines terminal               → completed
    otherwise                        → in_progress
```

Amended by [ADR-042](adr/ADR-042-refunds-voids-and-chargebacks.md) d1: an owed refund is checked first, and "all lines refunded" is gone (it fired only when refunds already covered the paid money). The only outputs that changed are an all-cancelled order and an all-refunded order whose refund failed: both read `partially_refunded` until the reissue.

Recomputed within the same transaction as any payment, line or refund change, under the lock order of §20.8. A failed or expired attempt leaves the order `pending_payment`, so it can be retried, until the hold release sets `cancelled_at`. "Refunds cover all paid money" counts pending and settled refunds plus what chargebacks applied, on the payment that reached paid, so the status does not change again on settlement. `late_capture` and voided refunds never count in any rule; a failed refund never counts toward `refunded`, and an owed (not reissued) one keeps the order `partially_refunded`; a mixed order whose physical line was cancelled with a refund and whose STL line was refunded is `refunded`. An unpaid cash order is `in_progress`; the API exposes derived `payment_due` and `can_cancel` flags so the customer and the "cash due" admin filter can tell it apart.

### 20.3 Order Line — Digital

```
pending ──> awaiting_delivery ──> delivered
   │               │                 │
   │               └──> refunded <───┘
   └──> cancelled (hold release of an unpaid order)
```

`awaiting_delivery` is entered atomically with payment verification. `delivered` is set by the administrator after emailing the file (§10.2) and is the terminal state for the order projection. Refunding a line in full while not yet delivered removes it from the delivery queue; a partial refund does not, and a failed refund changes no line state. `pending → cancelled` is used only by the hold release, and frees the STL ownership index.

### 20.4 Order Line — Physical (Delivery)

```
pending ──> in_production ──> ready_to_ship ──> shipped ──> delivered ──> refunded (paid)
   │             │                  │              │
   │             │                  │              ├──> cancelled (unpaid cash line totalling 0)
   │             │                  │              └──> returned ──> shipped (re-ship)
   │             │                  │                       ├──> in_production (reprint)
   │             │                  │                       ├──> refunded (paid line)
   │             │                  │                       └──> cancelled (unpaid cash line)
   └─> cancelled └─> cancelled      └─> cancelled
       (customer      (admin)           (admin)
        or admin)
```

`returned` is deliberately not terminal. `in_production` ("start printing") is internal and shown to the customer as "Received". Every edge requires a cash order or an online payment that reached `paid` (BR-148); the hold release's `pending → cancelled` is the only exception. Cancelling a paid line creates a refund obligation; cancelling an unpaid cash line does not. `returned → cancelled` is legal only for an unpaid cash line. An unpaid cash line with a total of 0 may also go `shipped → cancelled` (reason `other`), so an accepted $0 line is not recorded as a return. Admin cancels from `ready_to_ship` and `returned` record a cancel reason (`refused` or `other`). A line becomes `refunded` only when fully refunded, and an unfinished line is never refunded in full (it is cancelled instead). For a cash order, `shipped → delivered` happens only through the handover action (§9.8), for all live lines at once.

### 20.5 Order Line — Physical (Pickup)

```
pending ──> in_production ──> ready_for_pickup ──> picked_up ──> refunded (paid)
   │             │                   │
   └─> cancelled └─> cancelled       └─> cancelled (admin; no-show)
```

For a cash order, `ready_for_pickup → picked_up` happens only through the handover action. `ready_for_pickup → cancelled` records a cancel reason (`refused`, `no_show` or `other`); on an online order it creates a refund obligation and never blocks. On a cash order, the block rule of BR-144 applies.

### 20.6 Offer

```
                  ┌──> rejected (sets cooldown)
                  ├──> expired
awaiting_admin ───┴──> accepted ──┬──> paid
   ↑    │                 ↑       ├──> checkout_expired
   │    │                 │       └──> auto_closed
   │    │                 │ customer accepts on their own turn
   │    └──> awaiting_customer ──┐
   └─────────────────────────────┤ customer counters
                                 ├──> withdrawn
                                 └──> expired
```

Either party accepts on its own turn: the administrator from `awaiting_admin`, the customer from `awaiting_customer` (F-092, FR-13). Once accepted, only the checkout window applies.

`auto_closed` is reachable from every live state (`awaiting_admin`, `awaiting_customer`, `accepted`): buying the STL by another route closes any live offer (BR-088, §11.4; ADR-037).

### 20.7 Custom Request

```
new ──> contacted ──> quoted ──> in_progress ──> completed ──> closed
            └──> lost   └──> lost
```

### 20.8 Lock Order

Every write that changes an order's lines, payment or refunds locks the `orders` row first, then the lines it reads or changes in `id` order (refund and chargeback paths lock every line), then the payment row (refund and chargeback paths lock all of the order's payments by `id`), then the refund rows (`FOR UPDATE` or INSERT), then a chargeback's INSERT (ADR-042 d8), and recomputes the order status under those locks: line transitions, customer self-cancel, admin cancel, cash handover, payment apply (including late captures), payment retry, reconciliation marking an attempt failed or expired, manual confirmation, refund creation, settlement, failure, reissue and void, chargeback recording, record-capture, receipt confirmation and problem reports, and `release_stale_checkouts`. Nothing locks `payments` before `orders`, including batch selection: a job selects candidate ids without locking, then locks each order and re-reads. Locking a line before its order would deadlock against the handover, and two parallel line changes could each derive the order status from a stale view of the other (ADR-024). A payment that pays an STL then takes a transaction-scoped advisory lock on (customer, product) and that product's live offers by id, last (ADR-037); offer submission takes the same advisory lock, and offer checkout inserts its order before it locks the offer.

---

## 21. Database Schema

### 21.1 Conventions

| Concern      | Standard                                                                                                           |
| ------------ | ------------------------------------------------------------------------------------------------------------------ |
| Primary keys | UUID (time-ordered where available)                                                                                |
| Timestamps   | `timestamptz`, UTC always. Never naive — Lebanon observes DST, and naive datetimes shift every expiry twice a year |
| Money        | `bigint` cents plus `char(3)` currency, with non-negative checks                                                   |
| Soft delete  | `deleted_at` nullable; uniqueness via partial indexes                                                              |
| Enums        | Native PostgreSQL enum types                                                                                       |
| JSON         | `jsonb` exclusively                                                                                                |
| Migrations   | Alembic, forward-only, expand-contract                                                                             |

**Extensions:** pgcrypto, citext, pg_trgm, unaccent, btree_gin.

### 21.2 Invariants Enforced in the Database

Application checks provide good error messages; **database constraints provide the guarantee**. Under concurrency, application checks lose races that indexes do not.

| Constraint                                        | Enforces                 |
| ------------------------------------------------- | ------------------------ |
| Unique paid, unrefunded STL line per (user, product) | INV-18                |
| Unique live payment per order                     | INV-19                   |
| Unique live offer per (user, product)             | Offer concurrency        |
| Unique (cart, product)                            | INV-09                   |
| Unique review per (user, product) among live rows | BR-101                   |
| Unique email among live users                     | Account integrity        |
| Unique slug among live rows                       | INV-13                   |
| Unique (provider, event id) on webhooks           | Webhook idempotency      |
| Product type field check                          | Type integrity           |
| STL line quantity = 1                             | INV-08                   |
| Delivery requires address                         | Fulfillability           |
| Physical order requires contact phone             | BR-078                   |
| Cash payment requires recording administrator     | INV-22                   |
| One cash payment per order                        | INV-22                   |
| Cash order has only physical lines; cash payment only on a cash order | INV-21 |
| Rating between 1 and 5                            | BR-105                   |
| Non-negative money on every monetary column       | INV-01                   |

### 21.3 Indexing Strategy

Catalogue indexes are **partial**, filtered on non-deleted and visible rows — the only rows the storefront queries. This keeps them small and cache-resident.

| Index                                           | Serves                       |
| ----------------------------------------------- | ---------------------------- |
| (type, category, price) partial                 | Catalogue browse             |
| (type, material, colour, price) partial         | Facet filtering              |
| rating descending, partial                      | Top-rated sorting            |
| created descending, partial                     | Newest sorting               |
| GIN on search vector                            | Full-text search             |
| GIN trigram on name                             | Typo tolerance, autocomplete |
| (user, placed) on orders                        | Customer order history       |
| (status, placed) on orders                      | Admin queue                  |
| (placed) partial on unpaid cash orders          | Cash-due filter              |
| (user), (contact phone hash) partial on uncleared cash payment blocks | Cash eligibility |
| (fulfillment status, order) partial physical    | Fulfillment queue            |
| (placed) partial STL lines awaiting delivery    | STL delivery queue           |
| (status, responds_by) on offers                 | Expiry job                   |
| (send_after) partial pending outbox             | Email dispatch               |
| (status, initiated) partial processing payments | Reconciliation job           |
| (created, id) partial pending or owed refunds   | Obligations queue            |

### 21.4 Partitioning & Retention

| Table     | Strategy                 | Retention                                         |
| --------- | ------------------------ | ------------------------------------------------- |
| audit_log | Monthly range partitions | 24 months hot, then archived                      |

Partitions are created three months ahead by a scheduled job. **If partitions run out, audit inserts fail and every audited action fails with them** — this job must never be disabled.

### 21.5 Search Implementation

A generated `tsvector` column uses the `english` text-search configuration. Names are weighted above descriptions.

---

## 22. API Contract

### 22.1 Conventions

| Concern        | Standard                                                    |
| -------------- | ----------------------------------------------------------- |
| Base path      | `/api/v1` — versioned from day one                          |
| Authentication | httpOnly, Secure, SameSite cookies                          |
| CSRF           | Double-submit token on unsafe methods                       |
| Errors         | RFC 9457 `application/problem+json`                         |
| Pagination     | Cursor-based with `next_cursor`                             |
| Sorting        | Comma-separated field list with `-` prefix for descending   |
| Idempotency    | `Idempotency-Key` header on checkout and refunds            |
| Rate limits    | Standard `RateLimit-*` response headers                     |
| Money in JSON  | `{"amount_cents": int, "currency": string}` — never a float |

### 22.2 Error Contract

Every error carries a **stable machine-readable code**. The client renders its own message from the code, never from the human-readable detail. Changing a code value is a breaking API change.

### 22.3 Status Code Matrix

| Condition                                  | Status | Code                                                           |
| ------------------------------------------ | ------ | -------------------------------------------------------------- |
| Malformed body                             | 400    | MALFORMED_REQUEST                                              |
| Not authenticated                          | 401    | AUTH_REQUIRED                                                  |
| Email not verified                         | 403    | EMAIL_VERIFICATION_REQUIRED                                    |
| Not owner or not admin                     | 404    | NOT_FOUND (deliberately not 403 — avoids confirming existence) |
| Already owned                              | 409    | PRODUCT_ALREADY_OWNED                                          |
| Line or order not in a state for the action | 409   | INVALID_STATE_TRANSITION                                       |
| Live offer exists                          | 409    | OFFER_ALREADY_ACTIVE                                           |
| Idempotency key reused with different body | 409    | IDEMPOTENCY_KEY_CONFLICT                                       |
| Offer checkout window elapsed              | 410    | OFFER_CHECKOUT_EXPIRED                                         |
| Quantity over cap                          | 422    | QUANTITY_EXCEEDS_LIMIT                                         |
| Full refund of an unfinished physical line | 422    | REFUND_REQUIRES_CANCELLATION                                   |
| Offer below floor                          | 422    | OFFER_BELOW_MINIMUM                                            |
| Product not purchasable                    | 422    | PRODUCT_NOT_PURCHASABLE                                        |
| Cash chosen for an order with an STL line, or a zero total, or cash disabled; an unconfigured online provider chosen | 422 | PAYMENT_METHOD_NOT_ALLOWED |
| Cash total over limit                      | 422    | CASH_PAYMENT_LIMIT_REACHED                                     |
| Cash blocked, or open cash orders at the limit, for the customer or the phone (one body, no reason; ADR-038) | 422 | CASH_NOT_AVAILABLE |
| Cash entered differs from the amount due   | 422    | CASH_AMOUNT_MISMATCH                                           |
| Cooldown active                            | 422    | OFFER_COOLDOWN_ACTIVE                                          |
| Rate limited                               | 429    | RATE_LIMITED                                                   |
| Orders paused                              | 503    | ORDERS_PAUSED                                                  |

### 22.4 Endpoint Groups

**Public:** products list and detail, reviews, categories, materials, colours, search suggestions, custom requests, contact messages, public settings.

**Authentication:** register, login, logout, refresh, verify email, resend verification, password reset request and confirm.

**Customer:** profile, addresses, orders (including STL delivery status and payment due), order cancellation, receipt confirmation and problem report, cart operations, checkout, offers (create, counter, accept, withdraw, checkout), wishlist, reviews, notifications, data export, account deletion.

**Admin:** product CRUD, image management, STL delivery queue, categories, materials, colours, order queue and transitions, cash handover, cash payment blocks, refunds, offer management, custom request pipeline, contact messages, review moderation, settings, analytics, payment reconciliation.

**Webhook:** online payment provider callback (`/api/v1/webhooks/payments/{provider}`) — public, IP-allowlisted, signature-verified where available. Only configured online providers are routable: `cash` never, `mock` never in production; anything else is 404.

Admin routes are mounted on a separate router with separate authentication and rate limits. Sharing a namespace with public routes is how authorization mistakes happen.

---

## 23. Background Jobs

| Job                         | Cadence | Purpose and consequence of absence                                                                                                                           |
| --------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `dispatch_outbox`           | 1 min   | Delivers queued email with backoff. Without it, verification emails are lost and users are locked out entirely.                                              |
| `expire_offers`             | 5 min   | Expires offers whose turn deadline passed. Without it, negotiations never close.                                                                             |
| `release_stale_checkouts`   | 5 min   | Cancels unpaid online orders past hold only on an explicit `failed` or `expired` answer for the latest attempt; skips (and alerts on) every other answer, a failed or timed-out query, a provider without a status API, or an unprocessed webhook event; never touches cash orders. An administrator releases what it skips, from the hold deadline plus 24 h (ADR-036). Without it, abandoned checkouts hold their STLs until released by hand. |
| `reconcile_payments`        | 15 min  | Queries the provider for stuck online payments. **Most important job in the system** — without it a lost callback leaves a customer charged with nothing delivered. |
| `purge_unverified_accounts` | Daily   | Removes never-verified accounts.                                                                                                                             |
| `purge_expired_attachments` | Daily   | Deletes expired reference images from disk and database.                                                                                                     |
| `reap_orphan_files`         | Daily   | Reconciles filesystem against database. Filesystem writes are not transactional with Postgres, so orphans occur.                                             |
| `backup_verify`             | Daily   | Confirms backup integrity. A silently failing backup looks identical to a working one until the day it matters.                                              |
| `ensure_partitions`         | Monthly | Creates audit-log partitions three months ahead. If they run out, every audited action fails.                                                                |
| `purge_expired_security_records` | Daily | Deletes expired verification and reset tokens and ended sessions past their retention (VS-046). |
| `rotate_ip_salt`            | Daily check; rotates once per calendar month | Makes historical IP hashes unlinkable (ADR-028). |
| `verify_payments`           | 1 min   | Verifies unprocessed payment webhook events against the provider: the fallback for verification lost after the webhook's 200. Stuck payments with no event stay `reconcile_payments`' job (VS-024). Without it, a lost background task leaves a paid order unpaid until reconciliation (VS-023). |
| `purge_expired_idempotency_records` | Daily | Deletes idempotency claims past their 24 h life (VS-023). |

---

## 24. Infrastructure & Deployment

### 24.1 Services

nginx (TLS, static assets, first-line rate limiting), api (multiple workers), worker (job consumer), scheduler (cron), postgres, redis, clamav.

### 24.2 Volumes

`pgdata`, `uploads_private`, `media_public`, `backups`.

### 24.3 STL Files

None on the server (ADR-019). The STL files live on the administrator's own drive, and backing them up is the business's responsibility, outside the platform.

### 24.4 Secrets

Never committed. Environment file with restricted permissions or Docker secrets. Required: database URL, Redis URL, JWT signing key, CSRF secret, IP hash pepper (env; the rotating salts live in the database, ADR-028), phone hash salt (never rotated; cash blocks match on it), online payment provider credentials, webhook IP allowlist, email provider key, captcha secret, Sentry DSN, backup repository URL and encryption key.

**The backup encryption key must also be stored off the server.** An encrypted backup whose only key lives on the failed host is not a backup.

### 24.5 Backups

| Asset                   | Method                             | Cadence              | Target                    |
| ----------------------- | ---------------------------------- | -------------------- | ------------------------- |
| PostgreSQL              | Full plus continuous WAL archiving | Nightly + continuous | Off-server, S3-compatible |
| Uploads                 | Incremental snapshot               | Daily and on upload  | Off-server, encrypted     |
| Verification            | Automated integrity check          | Daily                | Alerts on failure         |
| Restore drill           | Manual, documented                 | Quarterly            | —                         |

**Recovery objectives:** RPO ≤5 minutes for database, ≤24 hours for files. RTO ≤4 hours, documented in a runbook.

### 24.6 Monitoring

Error tracking, uptime monitoring, **cron liveness monitoring** (alerts when a job stops running — the failure mode silent monitoring misses), host metrics, and business alerts for payments stuck in processing, outbox backlog, and disk above 80%.

Disk alerting is mandatory: uploads, logs, and WAL share one volume, and a full disk corrupts PostgreSQL.

### 24.7 CI/CD

Lint, type check, test, migration reversibility check, image build, deployment with health-check gating and one-command rollback. A staging environment is required — payment webhooks cannot be safely developed against production.

---

# PART D — QUALITY & GOVERNANCE

## 25. Non-Functional Requirements

| ID     | Requirement                                   | Target                                           |
| ------ | --------------------------------------------- | ------------------------------------------------ |
| NFR-01 | Catalogue page response                       | < 500 ms at p95                                  |
| NFR-02 | Search response                               | < 800 ms at p95                                  |
| NFR-03 | Checkout completion                           | < 2 s excluding provider redirect                |
| NFR-04 | Removed by ADR-019 (download initiation)      | —                                                |
| NFR-05 | Availability                                  | 99% monthly, single-host constraint acknowledged |
| NFR-06 | Concurrent users                              | 200 without degradation                          |
| NFR-07 | Catalogue scale                               | 10,000 products without index redesign           |
| NFR-08 | Responsive design                             | Mobile, tablet, desktop                          |
| NFR-10 | Data durability                               | RPO ≤5 min database, ≤24 h files                 |
| NFR-11 | Recovery time                                 | ≤4 hours                                         |
| NFR-12 | All timestamps UTC                            | Mandatory                                        |
| NFR-13 | Accessibility                                 | WCAG 2.1 AA target                               |

---

## 26. Security Requirements

| ID     | Requirement                                                               |
| ------ | ------------------------------------------------------------------------- |
| SEC-01 | Passwords hashed with Argon2id                                            |
| SEC-02 | Tokens in httpOnly, Secure, SameSite cookies                              |
| SEC-03 | CSRF protection on all unsafe methods                                     |
| SEC-04 | Admin MFA (strongly recommended, treated as required)                     |
| SEC-05 | Progressive delay and lockout on repeated auth failure                    |
| SEC-06 | Uniform responses to prevent email enumeration                            |
| SEC-07 | Single-use, short-lived, hashed reset and verification tokens             |
| SEC-08 | Session revocation on password change                                     |
| SEC-09 | Ownership verified on every resource fetch by ID                          |
| SEC-10 | Admin routes return 404 rather than 403 to non-admins                     |
| SEC-11 | Rate limiting on auth, reset, offers, reviews, forms, checkout            |
| SEC-12 | Captcha on all public unauthenticated forms                               |
| SEC-13 | Upload validation by content inspection, not extension                    |
| SEC-14 | All uploaded images re-encoded to strip payloads                          |
| SEC-15 | Malware scanning on every upload                                          |
| SEC-16 | Files stored outside the web root with generated names                    |
| SEC-17 | STL files never stored on or served by the platform (ADR-019)             |
| SEC-18 | Webhook signature verification where available                            |
| SEC-19 | Independent server-side verification of every online payment; cash recorded only by an administrator at handover |
| SEC-20 | Webhook idempotency by unique event identifier                            |
| SEC-21 | Server-side price authority; client amounts never trusted                 |
| SEC-22 | Output encoding and sanitisation of all user content                      |
| SEC-23 | Content Security Policy, HSTS, and security headers                       |
| SEC-24 | Parameterised queries throughout, including full-text search              |
| SEC-25 | Salted, rotating IP hashes                                                |
| SEC-26 | PII redaction in structured logs                                          |
| SEC-27 | Comprehensive audit logging                                               |
| SEC-28 | Secrets outside the repository, with off-site backup key storage          |
| SEC-29 | Containers run as non-root with resource limits                           |
| SEC-30 | TLS with automated certificate renewal                                    |

---

## 27. Testing Strategy

| Layer            | Scope                                                                                                                                                                   |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Unit**         | State machine transitions including illegal edges, money arithmetic, dispatch estimation                                                                                 |
| **Integration**  | Real PostgreSQL. **Every constraint asserted by attempting to violate it.** A mock or SQLite asserts nothing, because the invariants live in partial indexes and checks |
| **Contract**     | Payment adapter against a mock implementing every verification branch, including the no-status-API worst case                                                           |
| **End-to-end**   | Cart checkout through payment and STL delivery queue to delivered; offer through acceptance, one-time checkout, and payment; mixed order through partial refund; cash order through handover to completed; cash order refused (returned → cancelled, no refund, cash blocked for customer and phone); partly refused cash order (no block; refused line earns no revenue or badge); late provider success after hold release (refunded automatically, order untouched); failed refund stays owed and is reissued; chargeback recorded settled and split per line; full refund of an unfinished physical line refused (cancel instead) |
| **Concurrency**  | Parallel double-checkout (including the same STL twice, and two accounts sharing a phone against the open-cash-order limit), duplicate webhooks, self-cancel racing start printing on another line of the order, refund racing mark-delivered, two admins recording the same cash handover, cash handover racing an admin cancel or a line transition (no deadlock), two line changes on one order leaving the status correct, concurrent partial refunds, payment retry racing the hold release, refund racing a cash handover, two refusal cancels of the last two cash lines (one block), reconciliation batch running beside a handover (no deadlock), concurrent offer submission |
| **Security**     | IDOR sweep across every identified route, unverified-email write attempts, marking another customer's line delivered, confirming receipt on another customer's order, price tampering, cash chosen for an order with an STL line, webhooks to an unconfigured, `cash` or (in production) `mock` provider, a webhook whose provider differs from its payment's |

**Mandatory coverage:** the mixed-order partial-refund path, identified in audit as the most bug-prone area in the system.

---

## 28. Build Phases

| Phase                 | Contents                                                                                                    | Blocked by provider? |
| --------------------- | ----------------------------------------------------------------------------------------------------------- | -------------------- |
| **0 — Foundation**    | Migrations, auth, verification, i18n, admin shell, catalogue CRUD, search, settings, outbox, jobs           | No                   |
| **1 — Storefront**    | Public catalogue, product pages, reviews, wishlist, notifications, Bring Your Idea, contact, WhatsApp paths | No                   |
| **2 — Commerce**      | Cart, checkout, orders, fulfillment workflow, pickup, cash on delivery and handover, refunds — against mock provider | No          |
| **3 — Digital**       | STL delivery queue, offers                                                                                  | No                   |
| **4 — Payments live** | Online provider adapter, webhook, verification, reconciliation, manual confirmation                         | **Yes**              |
| **5 — Hardening**     | Rate limits, captcha, scanning, MFA, monitoring, backup drill, data rights, load test                       | No                   |

Phases 0–3 and 5 are fully unblocked. Only Phase 4 requires the provider decision (§30.4) and merchant credentials, and its interface is fixed by the adapter contract, making it a swap rather than a rewrite. Cash orders need no provider at all.

---

## 29. Risk Register

| #  | Severity     | Risk                                                                                    | Mitigation                                                                                      |
| -- | ------------ | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| 1  | **Critical** | Online provider not yet chosen or onboarded; gates all STL revenue and online physical revenue | Decide per §30.4 and apply immediately; develop against mock; cash orders sell physical goods meanwhile |
| 2  | **Critical** | Webhook authenticity unresolved — a forged callback would yield free goods              | Always re-query the provider server-side; never trust callback payload; idempotency by event ID |
| 3  | **High**     | Every V1 refund is manual (ADR-024); manual refunds and failed transfers get forgotten | Obligations queue lists pending and owed refunds until settled; alerts on late captures and chargeback excess |
| 4  | **High**     | Online prepaid plus made-on-demand — money held for goods that do not yet exist         | Lead times, quantity caps, availability toggle, kill switch, fast refund path                   |
| 19 | **High**     | Cash on delivery (ADR-024): goods are printed before payment, so fake or refused orders waste material and machine time | Cash switch, one open cash order per customer, 100 USD cash cap, contact phone to call before printing, a whole-order refusal blocks cash for the customer and phone, admin may cancel an unpaid line before it ships or after it is returned |
| 20 | **Medium**   | The courier holds collected cash between delivery and remittance; the platform records the cash when the courier reports it, not when it reaches the business | Record the full amount the customer paid; settle any shortfall with the courier regularly outside the platform; the cash-due filter and handover records show what each delivery should have collected |
| 5  | **High**     | Single host is a single point of failure for application and database                   | Tested off-server backups; storage abstraction enables rapid migration                          |
| 6  | **High**     | Email is critical-path — it gates every user action                                     | Reputable provider, SPF/DKIM, outbox with retry, monitoring, resend                             |
| 7  | **Medium**   | Mixed-order partial refunds are the most bug-prone path                                 | Per-line modelling from the start; mandatory heavy test coverage                                |
| 8  | **Medium**   | Manual fulfillment by one person; no tracking evidence for disputes                     | Internal notes, audit log, status emails, published policy                                      |
| 18 | **Medium**   | Manual STL delivery (ADR-019): slow or forgotten sends; email attachment limits (~20–25 MB) below bundle size; the admin's drive is the only copy of the files | Delivery queue oldest-first; customer notified on send; compress or send a storage link for large bundles; owner backs up the drive |
| 9  | **Medium**   | Open reviews permit fake ratings that poison Top Rated                                  | Verified badge, one per user, moderation, rate limiting                                         |
| 10 | **Medium**   | Single online payment provider; no fallback                                             | Provider abstraction ready for a second adapter; cash covers physical orders during an outage   |
| 11 | **Medium**   | Unauthenticated guest uploads on a host co-locating database and inventory              | Content validation, re-encoding, scanning, quotas, private storage, retention                   |
| 12 | **Medium**   | Disk exhaustion corrupts the database                                                   | Retention policies, partitioning, disk alerting above 80%                                       |
| 14 | **Medium**   | No product variants; colour requests divert to WhatsApp                                 | Accepted limitation; monitor WhatsApp volume for reconsideration                                |
| 15 | **Low-Med**  | International demand arrives while delivery is Lebanon-only                             | WhatsApp quotation path                                                                         |
| 16 | **Low-Med**  | No caching or CDN                                                                       | Monitor; add when metrics justify                                                               |
| 17 | **Low**      | Account deletion versus record retention tension                                        | Anonymise rather than purge; block while orders open                                            |

---

## 30. Open Decisions

None block the start of development. Each should close before its module is built.

### 30.1 Awaiting the Online Payment Provider

These questions apply to whichever provider §30.4 chooses; the Whish answers so far are noted.

| Item                                             | Impact                                                                                                                                                             |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Wallet-balance only, or general card acceptance? | **Determines whether the STL marketplace can serve customers outside Lebanon.** Whish's reply describes payment from a Whish balance; card acceptance is unconfirmed |
| Callback signature mechanism                     | Whether signature verification is active                                                                                                                           |
| Transaction status query API                     | Whether manual confirmation fallback is needed                                                                                                                     |
| Refund API or manual transfer                    | Resolved for V1 by ADR-024: every refund is manual; a provider refund API is not used even if offered |
| Sandbox environment                              | Blocks integration testing, not design                                                                                                                             |
| USD support and settlement timeline              | Cash flow planning                                                                                                                                                 |
| 3D Secure and dispute process                    | Fraud exposure (largely moot if wallet-only)                                                                                                                       |
| Merchant eligibility documents                   | **May reveal that business registration is the real blocker**                                                                                                      |
| Fees and commission rates                        | Margin calculation on STL pricing                                                                                                                                  |

### 30.2 Awaiting Client

| Item                                | Impact                                               |
| ----------------------------------- | ---------------------------------------------------- |
| Domain registration                 | Blocks the payment provider application, email SPF/DKIM, deployment |
| STL delivery time promise           | Text shown on STL pages and at checkout (ADR-019)    |
| Transactional email provider        | Critical-path infrastructure                         |
| Courier partner                     | Operations; the courier sets its own fee (ADR-024)   |
| Cash terms wording                  | Checkout consent text for cash orders and the refusal rule |
| Workshop pickup address and hours   | Settings values                                      |
| Pickup identity check policy        | Order number only, or identification?                |
| Refund baseline policy wording      | Published customer-facing text                       |
| Terms, Privacy, Refund page content | Legal requirement                                    |
| Invoicing legal requirements        | Accountant question                                  |
| Damaged-goods claim window          | Policy parameter                                     |
| Hosting provider and VPS sizing     | Deployment                                           |

### 30.3 Design-Time

| Item                                        | Impact                                                                                                           |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Session and token lifetimes                 | Security tuning                                                                                                  |
| Bring Your Idea attachment retention period | Storage and privacy                                                                                              |
| Analytics date ranges and export formats    | Dashboard scope                                                                                                  |
| Monitoring tooling selection                | Operations                                                                                                       |
| Frontend framework and rendering strategy   | **Outside backend scope; owned by the frontend team.** SEO requirements rule out a plain client-side application |

### 30.4 Online Payment Provider (ADR-024)

| Item                                         | Impact                                                                                                                                                                  | Due          |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| Whish, a card gateway, or both               | Which adapters VS-032 builds, the credentials and webhook allowlist, refund and status-query capabilities (§30.1). A card gateway should use a hosted or redirect payment page so card data never reaches the platform. If both are chosen, the customer picks one at checkout and it is snapshotted on the payment row | Before VS-032 |

---

## 31. Future Roadmap

**Near term:** international delivery; courier API integration with tracking numbers; customer invoice PDF download; abandoned-cart recovery; notification preferences and unsubscribe; bulk admin operations; tracking-number field.

**Medium term:** object storage migration with CDN; caching layer; second online payment provider (unless §30.4 already chooses two); product variants if WhatsApp volume justifies; 3D model preview for STL products; structured product Q&A; recommended print settings metadata; wishlist price-drop alerts; discount coupons; multi-admin roles.

**Long term:** mobile applications with push notifications; WhatsApp Business API for in-system tracking of manual orders; advanced analytics and reporting; commercial STL licensing; loyalty programme; gift cards; AI-assisted search and recommendations; additional languages; B2B enquiry path.

---

## 32. Glossary

| Term                      | Definition                                                                                   |
| ------------------------- | -------------------------------------------------------------------------------------------- |
| **Awaiting Delivery**     | State of a paid STL line until the administrator emails the file and marks it delivered      |
| **Batch Size**            | Units producible per lead-time cycle; drives dispatch estimation                             |
| **Bounded Context**       | A module owning its own tables and accessed only through service interfaces                  |
| **Bring Your Idea (BYI)** | The custom-printing lead workflow                                                            |
| **Cash Handover**         | The single admin action that records the cash collected for a cash order and marks its live lines delivered or picked up |
| **Cash on Delivery (COD)** | Payment method `cash` with delivery: the courier collects the amount due in cash at the door; at pickup it is paid at the counter |
| **Courier Delivery Fee**  | The fee the courier sets and collects from the customer on delivery; never part of the order total |
| **Idempotency Key**       | Client-supplied header preventing duplicate order or refund creation                         |
| **Kill Switch**           | Global setting pausing all new checkouts, online and cash, and new offer submissions         |
| **Lead Time**             | Days required to produce one batch of a physical product                                     |
| **Mixed Order**           | An order containing both digital and physical lines                                          |
| **Outbox**                | Table holding emails written inside a business transaction, delivered afterwards by a worker |
| **Paid Line**             | A line of an order whose payment reached paid, unless cancelled without a refund obligation (BR-149) |
| **Payment Method**        | Per-order choice at checkout: `online` or `cash`; distinct from Purchase Mode and Fulfillment Method |
| **Projection**            | A derived value maintained from other state; order status is one                             |
| **Purchase Mode**         | Per-product setting: Online Only, WhatsApp Only, or Both                                     |
| **Snapshot**              | Immutable copy of a value captured at order time                                             |
| **STL Delivery Queue**    | Admin list of paid STL lines awaiting delivery, oldest first (ADR-019)                       |
| **Soft Delete**           | Marking a record deleted without removing it                                                 |
| **Verified Purchase**     | Review badge indicating a genuine purchase record exists                                     |
| **Whish**                 | Lebanese payment provider; Whish Pay is its merchant service. A candidate online provider (§30.4) |

---

**End of Specification**

*This document is the single source of truth for Bekaa3D. Changes should be versioned, and material decisions recorded with their rationale so that context survives across sessions and across developers.*
