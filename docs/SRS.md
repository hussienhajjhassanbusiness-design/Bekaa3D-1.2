# Bekaa3D — Software Requirements Specification

**Version:** 1.1
**Date:** August 2026; revised 2026-10-06
**Revision 1.1:** STL files are delivered manually by email and never stored on the platform — see ADR-019.
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
| **A — Physical catalogue** | 3D-printed products, made on demand | Per product: online checkout, WhatsApp, or both |
| **B — STL marketplace**    | Digital model files                 | Online checkout only, emailed by the administrator |

### 1.2 Business Context

The business operates in Lebanon, where commerce remains substantially
relationship-based and cash-oriented. The platform's defining design decision —
**per-product purchase mode** — exists to respect this: products can be sold
through a modern online checkout, through a human WhatsApp conversation, or
both, at the administrator's discretion per item.

This is also the system's accessibility safeguard. Customers without a Whish
balance or card are never locked out; they use WhatsApp.

### 1.3 Scope of Version 1

**In scope:**

* English-language public storefront with SEO
* Physical product catalogue with three purchase modes
* STL digital marketplace; purchased files are emailed manually by the administrator (ADR-019)
* Cart supporting mixed digital + physical orders
* Online payment via Whish
* Manual fulfillment workflow (delivery and workshop pickup)
* Offer/negotiation system for STL products
* Reviews, wishlist, notifications
* Bring Your Idea lead workflow
* Admin dashboard with analytics
* Refunds with per-line partial support

**Explicitly out of scope for V1:**

* Product variants (colour/material selection at purchase) — routed to WhatsApp
* International shipping — routed to WhatsApp for quotation
* Courier API integration — fulfillment is manual
* Cash on delivery
* Guest checkout — account required for all purchases
* Product comments (distinct from reviews) — deferred
* BYI online payment — lead workflow only
* STL licensing management
* Storing, hosting, or automatically delivering STL files — they stay on the administrator's own drive (ADR-019)
* Mobile applications
* Tax/VAT calculation

### 1.4 Success Criteria

1. A customer can discover, evaluate, and purchase an STL file, then receive it by email from the administrator.
2. A customer can order a physical product online and track it to delivery or pickup.
3. A customer can reach the business via WhatsApp for anything the platform doesn't transact.
4. The administrator can operate the entire business from the dashboard without database access.
5. The English storefront is fully usable end to end. V1 is English-only — see ADR-016.
6. No payment can be granted without independent server-side verification.

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
| **Payment Provider (Whish)** | External                 | Payment processing, webhook callbacks, status queries                                                                                    |
| **Courier**                  | External, outside system | Physical delivery. **Not a system user** — no tracking integration in V1                                                                 |

### 2.2 The Verification Boundary

**Browsing is open. Acting requires a verified email.**

| Action class                                      | Requirement                            |
| ------------------------------------------------- | -------------------------------------- |
| View catalogue, product, reviews, search          | None                                   |
| Submit Bring Your Idea, contact form              | Captcha + rate limit (guest permitted) |
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
| BR-027 | Delivery address and shipping fee are required only when the cart contains at least one physical line.         |

### 3.3 Checkout & Orders

| ID     | Rule                                                                                                                               |
| ------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| BR-030 | Checkout requires a verified account. There is no guest checkout.                                                                  |
| BR-031 | All prices, shipping, and totals are recomputed server-side; client-supplied amounts are never trusted.                            |
| BR-032 | Each order carries a human-readable order number.                                                                                  |
| BR-033 | Order lines snapshot product name, price, and image at purchase; later catalogue edits never alter order history. |
| BR-034 | An order's fulfillment method is Delivery, Pickup, or none (digital-only orders).                                                  |
| BR-035 | Order status is a derived projection of payment status and line statuses; it is never set directly.                                |
| BR-036 | Each order line carries its own fulfillment status.                                                                                |
| BR-037 | Estimated dispatch date = max across physical lines of (lead time × ceil(quantity ÷ batch size)).                                  |
| BR-038 | Customers are promised an estimated **dispatch** date, never a delivery date; courier transit is outside the company's control.    |
| BR-039 | Unpaid checkouts expire after a configurable hold period and are cancelled automatically.                                          |
| BR-040 | The global "accepting orders" kill switch blocks new checkouts but never affects payments already in flight.                       |
| BR-041 | Checkout is idempotent; a repeated request with the same idempotency key returns the original order.                               |
| BR-042 | Digital lines enter `awaiting_delivery` on payment verification and are fulfilled when the administrator emails the file and marks the line delivered, independently of physical lines. |

### 3.4 Payments

| ID     | Rule                                                                                                                          |
| ------ | ----------------------------------------------------------------------------------------------------------------------------- |
| BR-050 | All prices are in USD.                                                                                                        |
| BR-051 | Money is stored as integer cents with an explicit currency code; floats are never used.                                       |
| BR-052 | Whish is the sole payment provider in V1, behind a provider abstraction.                                                      |
| BR-053 | A payment callback is a notification, never proof of payment.                                                                 |
| BR-054 | Payment is confirmed only by independent server-side verification (status query or, failing that, manual admin confirmation). |
| BR-055 | The confirmed amount must match the order total; a lesser amount is never treated as paid.                                    |
| BR-056 | Duplicate webhook deliveries are idempotent and never apply a payment twice.                                                  |
| BR-057 | Nothing is delivered or produced before confirmed payment — no STL is sent, nothing is manufactured.                          |
| BR-058 | At most one live payment attempt may exist per order; a retry is permitted only after the prior attempt fails or expires.     |
| BR-059 | No tax is applied in V1; the price shown is the price charged.                                                                |

### 3.5 Refunds & Cancellation

| ID     | Rule                                                                                                                             |
| ------ | -------------------------------------------------------------------------------------------------------------------------------- |
| BR-060 | STL purchases are final; this is presented and consent is recorded at checkout.                                                  |
| BR-061 | Physical orders are refundable at the administrator's discretion, on a published baseline policy.                                |
| BR-062 | Refunds may be partial and per-line, including shipping.                                                                         |
| BR-063 | Every refund creates a tracked obligation record that remains pending until settled.                                             |
| BR-064 | A refunded digital line is marked refunded; if it has not been sent yet it leaves the delivery queue and must not be sent.       |
| BR-065 | A file already emailed cannot be recalled; the protections are the all-sales-final consent record and the delivery record.     |
| BR-066 | A customer may cancel their own order while it is paid but not yet in production.                                                |
| BR-067 | Once a line enters production, self-cancellation closes and cancellation becomes an admin decision.                              |
| BR-068 | STL lines are never self-cancellable.                                                                                            |
| BR-069 | A customer whose STL line was refunded may purchase the product again.                                                           |

### 3.6 Shipping & Fulfillment

| ID     | Rule                                                                           |
| ------ | ------------------------------------------------------------------------------ |
| BR-070 | Shipping uses admin-managed zones with flat rates.                             |
| BR-071 | Only Lebanese zones are enabled in V1.                                         |
| BR-072 | International customers are directed to WhatsApp for a quotation.              |
| BR-073 | Workshop pickup is offered, is free, and requires no address.                  |
| BR-074 | Shipping fee and zone are snapshotted onto the order.                          |
| BR-075 | Fulfillment is entirely manual; no courier integration exists in V1.           |
| BR-076 | An optional free-shipping threshold may be configured.                         |
| BR-077 | A returned item is not terminal; it may be re-shipped, reprinted, or refunded. |

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
| BR-102 | Reviews backed by a real purchase display a Verified Purchase badge.                      |
| BR-103 | WhatsApp-only products can never earn the badge, as no purchase record exists.            |
| BR-104 | The badge is recomputed when a purchase is paid or refunded.                              |
| BR-105 | Ratings are 1–5 integers.                                                                 |
| BR-106 | The administrator may hide or restore any review.                                         |
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
| F-033 | Self-service order cancellation (pre-production) | 2     |
| F-034 | Data export (JSON)                               | 5     |
| F-035 | Account deletion via anonymisation               | 5     |

### 4.3 Commerce

| ID    | Feature                                                     | Phase |
| ----- | ----------------------------------------------------------- | ----- |
| F-040 | Mixed cart (digital + physical)                             | 2     |
| F-041 | Quantity management with per-product caps                   | 2     |
| F-042 | Price-change detection and confirmation at checkout         | 2     |
| F-043 | Shipping zone selection and fee calculation                 | 2     |
| F-044 | Workshop pickup option                                      | 2     |
| F-045 | Free-shipping threshold                                     | 2     |
| F-046 | Idempotent checkout                                         | 2     |
| F-047 | Whish payment redirect and return handling                  | 4     |
| F-048 | Webhook receipt with signature verification where available | 4     |
| F-049 | Independent server-side payment verification                | 4     |
| F-050 | Payment reconciliation for missed callbacks                 | 4     |
| F-051 | Manual payment confirmation fallback                        | 4     |
| F-052 | Order confirmation with terms consent capture               | 2     |

### 4.4 Fulfillment

| ID    | Feature                                                             | Phase |
| ----- | ------------------------------------------------------------------- | ----- |
| F-060 | Order queue with status filters and search                          | 2     |
| F-061 | Per-line fulfillment status transitions                             | 2     |
| F-062 | Internal admin notes on orders                                      | 2     |
| F-063 | Delivery workflow: production → ready to ship → shipped → delivered | 2     |
| F-064 | Pickup workflow: production → ready for pickup → picked up          | 2     |
| F-065 | Return handling with re-ship, reprint, or refund                    | 2     |
| F-066 | Order cancellation by admin                                         | 2     |
| F-067 | Estimated dispatch date calculation                                 | 2     |
| F-068 | Global accepting-orders kill switch                                 | 2     |

### 4.5 Refunds

| ID    | Feature                                            | Phase |
| ----- | -------------------------------------------------- | ----- |
| F-070 | Full and partial per-line refunds                  | 2     |
| F-071 | Shipping fee refund                                | 2     |
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
| F-113 | Shipping zone management                    | 2     |
| F-114 | Typed settings editor                       | 0     |
| F-116 | User management                             | 0     |
| F-117 | Audit log viewer                            | 5     |
| F-118 | Admin MFA                                   | 5     |

### 4.10 Analytics

| ID    | Feature                                                  | Phase |
| ----- | -------------------------------------------------------- | ----- |
| F-120 | Revenue by stream (physical vs STL), attributed per line | 2     |
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
7. Redirected to Whish, completes payment.
8. System independently verifies the payment.
9. The STL line enters the admin's delivery queue; confirmation email and notification sent, saying the file will be emailed.
10. The administrator emails the file from their own drive to the customer's account email and marks the line delivered.
11. The customer is notified that the file has been sent. A lost file is re-sent on request, outside the system.

### 5.2 Purchase a Physical Product Online

1. Visitor browses the physical catalogue.
2. Opens a product configured Online Only or Both.
3. Sees price, production lead time, and estimated dispatch.
4. Registers and verifies, adds to cart with quantity within the cap.
5. At checkout chooses delivery (with address and zone fee) or free workshop pickup.
6. Server recomputes all totals; customer accepts terms.
7. Pays via Whish; system verifies independently.
8. Order enters the admin queue.
9. Admin marks in production → ready → shipped or ready for pickup.
10. Customer receives status emails and notifications throughout.
11. Admin marks delivered or picked up; order completes.

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
2. Single payment covers both; delivery address required for the physical line.
3. On verification: the STL line enters the delivery queue; physical line enters production.
4. A printer failure makes the physical item unproducible.
5. Admin cancels that line and issues a partial refund covering it and shipping.
6. The STL line is unaffected; the administrator still sends (or has already sent) the file.
7. Order status becomes Partially Refunded; the refund is tracked until settled.

---

# PART B — FUNCTIONAL SPECIFICATION

## 6. Catalogue & Search

### 6.1 Product Attributes

**Common to both types:** name, description, category, price, multiple images, visibility flag, featured flag, availability toggle, SEO metadata (title, description, OG image, slug). Catalogue text lives in plain columns on the owning table — V1 is English-only, see ADR-016 and §17.2.

**Physical only:** purchase mode, material, colour, dimensions, production lead time (days), batch size, maximum quantity per line, weight (optional, reserved for future weight-based shipping).

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
7. Determine fulfillment method; require address for delivery.
8. Resolve the shipping zone and rate; apply free-shipping threshold if configured.
9. **Recompute all totals server-side.**
10. Create order, order items with snapshots, and a pending payment.
11. Compute the estimated dispatch date.
12. Clear the cart.
13. Record terms consent with timestamp.

### 7.4 Conditional Requirements

| Cart contents      | Address      | Shipping fee | Fulfillment method |
| ------------------ | ------------ | ------------ | ------------------ |
| STL only           | Not required | None         | None (null)        |
| Physical, delivery | Required     | Zone rate    | Delivery           |
| Physical, pickup   | Not required | Free         | Pickup             |
| Mixed, delivery    | Required     | Zone rate    | Delivery           |
| Mixed, pickup      | Not required | Free         | Pickup             |

### 7.5 Idempotency

Checkout requires an `Idempotency-Key` header. A repeated key with a matching request body returns the stored response; a mismatched body returns 409. This is what prevents a double-clicked checkout from creating two orders and two payment attempts.

---

## 8. Orders & Fulfillment

### 8.1 Order Composition

An order carries: order number, customer, source (cart or offer), derived status, fulfillment method, monetary breakdown (subtotal, shipping, tax=0, total, currency), address snapshot, shipping zone and rate snapshot, customer note, internal admin note, estimated dispatch date, and lifecycle timestamps.

Each line carries: product reference, type, name snapshot, image snapshot, unit price, quantity, line total, its own fulfillment status, lead time and batch size snapshots, and an optional offer reference.

### 8.2 Why Per-Line Status

A mixed order can have its physical half cancelled while the digital half still awaits delivery or has been sent. A single order-level status cannot express this. Per-line status is therefore mandatory, and the order header status is computed from the lines.

### 8.3 Delivery Workflow

`pending` → `in_production` → `ready_to_ship` → `shipped` → `delivered`

Exits: cancellation before production (customer or admin) or during production (admin only, creating a refund obligation). From `shipped`, a failed delivery moves to `returned`, which may then be re-shipped, reprinted, or refunded. From `delivered`, an upheld claim moves to `refunded`.

### 8.4 Pickup Workflow

`pending` → `in_production` → `ready_for_pickup` → `picked_up`

Payment has already occurred online, so no money changes hands at handover. The workshop address and hours are configurable settings displayed at checkout and in the ready-for-pickup notification.

### 8.5 The Cancellation Cutoff

Entering production is the boundary. Before it, the customer may self-cancel. After it, cancellation requires admin action because material and machine time have been committed.

This transition and a customer self-cancellation contend for the same row lock, so exactly one wins — the race cannot leave the order in an ambiguous state.

### 8.6 Dispatch Estimation

`dispatch_days = max over physical lines of (lead_time_days × ceil(quantity ÷ batch_size))`

Batch size matters: if one print takes six hours and four fit on the bed, ten units is three cycles, not ten. A naive `max(lead_time)` would systematically understate multi-unit orders — precisely the orders where a missed date causes the most damage.

### 8.7 Admin Capabilities

View and filter the queue; inspect customer and order detail; transition line statuses; add internal notes (never customer-visible); cancel lines or orders; issue refunds; view the pending-refund obligations queue; work the STL delivery queue (§10.2).

---

## 9. Payments & Refunds

### 9.1 Provider Abstraction

All payment interaction sits behind a provider interface: create payment, query status, issue refund (where supported), verify webhook signature (where supported). Whish is the first adapter; a mock adapter enables full development and testing without credentials. Additional providers require no changes outside their adapter.

### 9.2 Verification — the Critical Path

**Governing rule: a callback is a notification, never proof.**

The webhook endpoint is public. If it were trusted, a forged callback would get STL files emailed and goods manufactured for free. The verification sequence is therefore:

1. **Receive and persist** the webhook event immediately. A unique constraint on (provider, event id) makes duplicate delivery harmless — this is the idempotency mechanism.
2. **Return 200 quickly.** Providers retry on timeout; slow processing multiplies deliveries.
3. **Verify the signature** if the provider offers one. Failure rejects and alerts.
4. **Independently query** the provider for transaction status, holding no database locks.
5. **Confirm the amount matches** the order total exactly. A lesser amount is never treated as paid.
6. **Apply the result** in a second transaction: mark paid, move STL lines to `awaiting_delivery`, move physical lines to production, close any live offer, recompute the order projection, write audit and history, enqueue emails.

If the provider offers no status query, the event is queued for **manual admin confirmation** against the provider dashboard. Slower, but a forged callback still yields nothing.

### 9.3 Missed Callbacks

A scheduled reconciliation job queries the provider for any payment stuck in processing beyond a threshold. Without it, a lost callback leaves a customer charged with nothing delivered and no recovery path — the single worst failure mode in the system.

### 9.4 One Live Payment Per Order

A database constraint permits only one payment in pending, processing, or paid state per order. A retry requires the prior attempt to have failed or expired, which is what the checkout-release job provides.

### 9.5 Refund Policy

| Product type | Policy                                                                                                                                                                          |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| STL          | All sales final. Consent recorded at checkout with timestamp.                                                                                                                   |
| Physical     | Admin discretion on a published baseline: full refund before production; damaged, wrong, or undelivered resolved by replacement or refund with evidence within a stated window. |

### 9.6 Refund Execution

Refunds may cover any subset of lines plus shipping. Each creates a refund record with amount, currency, reason, requester, approver, method, and settlement state. Digital lines in a refund become `refunded`; one not yet sent leaves the delivery queue.

The record remains a **tracked pending obligation** until settled. If the provider has no refund API, settlement is a manual transfer — exactly the kind of task that gets forgotten without a queue driving it.

### 9.7 Chargeback Handling

A confirmed reversal marks the affected STL lines refunded (removing any not yet sent from the delivery queue) and audits the event. A file already emailed cannot be recalled; the mitigations are the recorded consent and the delivery record as evidence.

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

A refunded STL line becomes `refunded`. If it was still awaiting delivery, it leaves the queue and must not be sent. If it was already sent, the file cannot be recalled; the protections are the all-sales-final consent recorded at checkout and the delivery record. A customer whose line was refunded may buy the product again.

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

The badge is **recomputed** when a purchase is paid or refunded — a cached flag written once would leave a refunded buyer displaying credibility they no longer hold.

WhatsApp-only products can never earn the badge, since no purchase record exists. This is a known and accepted bias.

### 12.2 Rating Aggregates

Average rating and review count are maintained aggregates on the product, recalculated on review creation, edit, deletion, and moderation. Computing them on demand across a growing table would not survive catalogue growth.

### 12.3 Wishlist

Verified users add and remove products. The admin sees total wishlist counts and most-wishlisted products, informing promotion decisions. Price-drop alerts are deferred to a future version.

### 12.4 Notifications

An in-app notification centre complements email. Types include offer updates, purchase confirmation, STL file sent, order status changes, and account events. Each carries a type, JSON payload, and read state.

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

Multiple saved addresses with a default. Fields: label, recipient name, phone, governorate, city, area, street, and **landmark notes** — Lebanese addressing is landmark-based, so free-text notes are functionally required rather than decorative.

### 14.5 Data Rights

**Export:** JSON containing profile, addresses, orders (with STL delivery records), reviews, and offers.

**Deletion:** implemented as anonymisation. Login is disabled and personal data stripped, but financial and delivery records are retained in anonymised form — required for accounting and referential integrity. Deletion is blocked while orders are open or refunds unsettled, since fulfilling an order requires the name and address.

---

## 15. Admin Dashboard

### 15.1 Catalogue Management

Product CRUD for both types; image upload, reorder, and cover selection; category, material, and colour management; visibility, featured, and availability toggles; SEO metadata; marking STL lines delivered.

### 15.2 Order Management

Filterable queue by status, date, customer, and fulfillment method; order detail with customer information; per-line status transitions; internal notes; cancellation; refund issuance.

### 15.3 Queues

STL lines awaiting delivery; Bring Your Idea pipeline; contact messages; pending offers; pending refund obligations; payments requiring manual confirmation; review moderation.

### 15.4 Settings

Typed, admin-editable configuration with audit trail. At minimum: accepting-orders kill switch, offer response window, offer checkout window, rejection cooldown, minimum offer percentage, checkout hold period, unverified purge period, free-shipping threshold, pickup address and hours, WhatsApp number.

These are settings rather than constants specifically so operational changes never require a deployment.

### 15.5 Analytics

**Revenue must be attributed per line item**, not per order — a mixed order would otherwise corrupt the STL revenue figure the business relies on.

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
| Order confirmation          | Customer  |
| Payment receipt             | Customer  |
| STL file sent               | Customer  |
| Order in production         | Customer  |
| Order shipped               | Customer  |
| Ready for pickup            | Customer  |
| Order delivered / picked up | Customer  |
| Order cancelled             | Customer  |
| Refund issued               | Customer  |
| Offer countered             | Customer  |
| Offer accepted              | Customer  |
| Offer rejected              | Customer  |
| Offer expiring soon         | Customer  |

WhatsApp-only orders generate no system email — those conversations happen entirely off-platform.

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
| Ordering       | Cart, orders, order items, status history                           |
| Payments       | Payment attempts, webhook events, refunds                           |
| Fulfillment    | Shipping zones, fulfillment transitions, STL delivery               |
| Negotiation    | Offers, offer rounds                                                |
| Engagement     | Reviews, wishlist, notifications, custom requests, contact messages |
| Platform       | Settings, audit log, email outbox, idempotency records              |

Cross-context access goes through service interfaces. Direct joins into another context's tables are prohibited — that practice is what turns "Clean Architecture" into folder decoration.

### 18.4 Key Abstractions

| Abstraction              | Purpose                                               |
| ------------------------ | ----------------------------------------------------- |
| Payment provider port    | Whish today, any provider later, mock for development |
| Storage port             | Local filesystem today, S3-compatible later           |
| Email provider port      | Provider-agnostic transactional delivery              |
| Captcha port             | Provider-agnostic verification                        |
| Repository per aggregate | Persistence isolated from domain logic                |

---

## 19. Domain Model

### 19.1 Entity Inventory

**Identity:** User, Address, Session, VerificationToken, PasswordResetToken

**Catalog:** Product, ProductImage, Category, Material, Colour

**Ordering:** Cart, CartItem, Order, OrderItem, OrderStatusHistory

**Payments:** Payment, WebhookEvent, Refund, RefundItem

**Fulfillment:** ShippingZone

**Negotiation:** Offer, OfferRound

**Engagement:** Review, WishlistItem, Notification, CustomRequest, CustomRequestAttachment, ContactMessage

**Platform:** Setting, AuditLog, EmailOutbox, IdempotencyRecord

### 19.2 Core Invariants

Numbered for traceability. `INV-` prefix.

**Money**

* INV-01 — All monetary values are integer cents with an explicit currency code.
* INV-02 — Prices, shipping, and totals are always recomputed server-side.
* INV-03 — Order and line snapshots are immutable after placement.

**STL delivery**

* INV-04 — An STL is never sent before its payment is verified; only a line in `awaiting_delivery` can be marked delivered.
* INV-05 — STL lines enter `awaiting_delivery` atomically with payment verification.
* INV-06 — Marking a line delivered or refunded never deletes it; it sets a timestamp.

**Ordering**

* INV-07 — Lines whose product is WhatsApp-only, invisible, unavailable, or deleted are rejected at checkout.
* INV-08 — STL lines have quantity exactly 1 and are rejected when the customer already owns the STL (§10.3).
* INV-09 — A cart holds at most one line per product; merged quantity respects the cap.
* INV-10 — The kill switch blocks new checkouts but never in-flight payments.
* INV-11 — Dispatch estimate accounts for quantity and batch size.

**Content**

* INV-12 — Product name is required.
* INV-13 — Slugs are unique among non-deleted rows.

**Security**

* INV-14 — Every write action requires a verified email.
* INV-15 — Every fetch by ID verifies ownership or admin role.
* INV-16 — STL files are never stored on or served by the platform.

**Consistency**

* INV-17 — Verified Purchase badges recompute when a purchase is paid or refunded.
* INV-18 — At most one paid, unrefunded STL line per (customer, product); a refunded buyer may re-purchase.
* INV-19 — At most one live payment per order.
* INV-20 — Order status is a projection, never assigned directly.

---

## 20. State Machines

### 20.1 Payment

```
pending ──> processing ──> paid ──> partially_refunded ──> refunded
   │             │           └────────────────────────────> refunded
   │             ├──> failed
   └──> expired  └──> expired
```

`paid` is reachable only through independent server-side verification.

### 20.2 Order Status (derived projection)

```
payment pending or processing        → pending_payment
payment failed or expired            → cancelled
payment paid:
    all lines cancelled              → cancelled
    all lines refunded               → refunded
    any refund present               → partially_refunded
    all lines terminal               → completed
    otherwise                        → in_progress
```

Recomputed within the same transaction as any payment or line change.

### 20.3 Order Line — Digital

```
pending ──> awaiting_delivery ──> delivered
                   │                 │
                   └──> refunded <───┘
```

`awaiting_delivery` is entered atomically with payment verification. `delivered` is set by the administrator after emailing the file (§10.2) and is the terminal state for the order projection. Refunding a line not yet delivered removes it from the delivery queue.

### 20.4 Order Line — Physical (Delivery)

```
pending ──> in_production ──> ready_to_ship ──> shipped ──> delivered ──> refunded
   │             │                    ↑            │
   └─> cancelled └─> cancelled        └── returned ┘
                                          └──> in_production (reprint)
                                          └──> refunded
```

`returned` is deliberately not terminal.

### 20.5 Order Line — Physical (Pickup)

```
pending ──> in_production ──> ready_for_pickup ──> picked_up ──> refunded
```

### 20.6 Offer

```
                  ┌──> rejected (sets cooldown)
awaiting_admin ───┼──> accepted ──> paid
   ↑    │         └──> expired         └──> checkout_expired
   │    └──> awaiting_customer ──┐     └──> auto_closed
   └───────────────────────────  ┤
                                 ├──> withdrawn
                                 └──> expired
```

Once accepted, only the checkout window applies.

### 20.7 Custom Request

```
new ──> contacted ──> quoted ──> in_progress ──> completed ──> closed
            └──> lost   └──> lost
```

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
| (fulfillment status, order) partial physical    | Fulfillment queue            |
| (placed) partial STL lines awaiting delivery    | STL delivery queue           |
| (status, responds_by) on offers                 | Expiry job                   |
| (send_after) partial pending outbox             | Email dispatch               |
| (status, initiated) partial processing payments | Reconciliation job           |
| (created) partial pending refunds               | Obligations queue            |

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
| Live offer exists                          | 409    | OFFER_ALREADY_ACTIVE                                           |
| Idempotency key reused with different body | 409    | IDEMPOTENCY_KEY_CONFLICT                                       |
| Offer checkout window elapsed              | 410    | OFFER_CHECKOUT_EXPIRED                                         |
| Quantity over cap                          | 422    | QUANTITY_EXCEEDS_LIMIT                                         |
| Offer below floor                          | 422    | OFFER_BELOW_MINIMUM                                            |
| Product not purchasable                    | 422    | PRODUCT_NOT_PURCHASABLE                                        |
| Cooldown active                            | 422    | OFFER_COOLDOWN_ACTIVE                                          |
| Rate limited                               | 429    | RATE_LIMITED                                                   |
| Orders paused                              | 503    | ORDERS_PAUSED                                                  |

### 22.4 Endpoint Groups

**Public:** products list and detail, reviews, categories, materials, colours, search suggestions, custom requests, contact messages, public settings.

**Authentication:** register, login, logout, refresh, verify email, resend verification, password reset request and confirm.

**Customer:** profile, addresses, orders (including STL delivery status), order cancellation, cart operations, checkout, offers (create, counter, accept, withdraw, checkout), wishlist, reviews, notifications, data export, account deletion.

**Admin:** product CRUD, image management, STL delivery queue, categories, materials, colours, shipping zones, order queue and transitions, refunds, offer management, custom request pipeline, contact messages, review moderation, settings, analytics, payment reconciliation.

**Webhook:** payment provider callback — public, IP-allowlisted, signature-verified where available.

Admin routes are mounted on a separate router with separate authentication and rate limits. Sharing a namespace with public routes is how authorization mistakes happen.

---

## 23. Background Jobs

| Job                         | Cadence | Purpose and consequence of absence                                                                                                                           |
| --------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `dispatch_outbox`           | 1 min   | Delivers queued email with backoff. Without it, verification emails are lost and users are locked out entirely.                                              |
| `expire_offers`             | 5 min   | Expires offers whose turn deadline passed. Without it, negotiations never close.                                                                             |
| `release_stale_checkouts`   | 5 min   | Cancels unpaid orders past hold. Without it, the one-live-payment constraint permanently blocks retry.                                                       |
| `reconcile_payments`        | 15 min  | Queries the provider for stuck payments. **Most important job in the system** — without it a lost callback leaves a customer charged with nothing delivered. |
| `purge_unverified_accounts` | Daily   | Removes never-verified accounts.                                                                                                                             |
| `purge_expired_attachments` | Daily   | Deletes expired reference images from disk and database.                                                                                                     |
| `reap_orphan_files`         | Daily   | Reconciles filesystem against database. Filesystem writes are not transactional with Postgres, so orphans occur.                                             |
| `backup_verify`             | Daily   | Confirms backup integrity. A silently failing backup looks identical to a working one until the day it matters.                                              |
| `ensure_partitions`         | Monthly | Creates audit-log partitions three months ahead. If they run out, every audited action fails.                                                                |
| `rotate_ip_salt`            | Monthly | Makes historical IP hashes unlinkable.                                                                                                                       |

---

## 24. Infrastructure & Deployment

### 24.1 Services

nginx (TLS, static assets, first-line rate limiting), api (multiple workers), worker (job consumer), scheduler (cron), postgres, redis, clamav.

### 24.2 Volumes

`pgdata`, `uploads_private`, `media_public`, `backups`.

### 24.3 STL Files

None on the server (ADR-019). The STL files live on the administrator's own drive, and backing them up is the business's responsibility, outside the platform.

### 24.4 Secrets

Never committed. Environment file with restricted permissions or Docker secrets. Required: database URL, Redis URL, JWT signing key, CSRF secret, IP hash salt, Whish channel and secret, webhook IP allowlist, email provider key, captcha secret, Sentry DSN, backup repository URL and encryption key.

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
| SEC-19 | Independent server-side payment verification always                       |
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
| **End-to-end**   | Cart checkout through payment and STL delivery queue to delivered; offer through acceptance, one-time checkout, and payment; mixed order through partial refund         |
| **Concurrency**  | Parallel double-checkout (including the same STL twice), duplicate webhooks, self-cancel racing production start, refund racing mark-delivered, concurrent offer submission |
| **Security**     | IDOR sweep across every identified route, unverified-email write attempts, marking another customer's line delivered, price tampering                                                |

**Mandatory coverage:** the mixed-order partial-refund path, identified in audit as the most bug-prone area in the system.

---

## 28. Build Phases

| Phase                 | Contents                                                                                                    | Blocked by Whish? |
| --------------------- | ----------------------------------------------------------------------------------------------------------- | ----------------- |
| **0 — Foundation**    | Migrations, auth, verification, i18n, admin shell, catalogue CRUD, search, settings, outbox, jobs           | No                |
| **1 — Storefront**    | Public catalogue, product pages, reviews, wishlist, notifications, Bring Your Idea, contact, WhatsApp paths | No                |
| **2 — Commerce**      | Cart, checkout, orders, fulfillment workflow, shipping zones, pickup, refunds — against mock provider       | No                |
| **3 — Digital**       | STL delivery queue, offers                                                                                  | No                |
| **4 — Payments live** | Whish adapter, webhook, verification, reconciliation, manual confirmation                                   | **Yes**           |
| **5 — Hardening**     | Rate limits, captcha, scanning, MFA, monitoring, backup drill, data rights, load test                       | No                |

Phases 0–3 and 5 are fully unblocked. Only Phase 4 requires merchant credentials, and its interface is fixed by the adapter contract, making it a swap rather than a rewrite.

---

## 29. Risk Register

| #  | Severity     | Risk                                                                                    | Mitigation                                                                                      |
| -- | ------------ | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| 1  | **Critical** | Whish onboarding incomplete; gates all revenue on both halves                           | Apply immediately via the Whish app; develop against mock; phase delivery                       |
| 2  | **Critical** | Webhook authenticity unresolved — a forged callback would yield free goods              | Always re-query the provider server-side; never trust callback payload; idempotency by event ID |
| 3  | **High**     | Refund mechanism unknown; manual refunds get forgotten                                  | Confirm during onboarding; system tracks obligations until settled                              |
| 4  | **High**     | Prepaid plus made-on-demand — money held for goods that do not yet exist                | Lead times, quantity caps, availability toggle, kill switch, fast refund path                   |
| 5  | **High**     | Single host is a single point of failure for application and database                   | Tested off-server backups; storage abstraction enables rapid migration                          |
| 6  | **High**     | Email is critical-path — it gates every user action                                     | Reputable provider, SPF/DKIM, outbox with retry, monitoring, resend                             |
| 7  | **Medium**   | Mixed-order partial refunds are the most bug-prone path                                 | Per-line modelling from the start; mandatory heavy test coverage                                |
| 8  | **Medium**   | Manual fulfillment by one person; no tracking evidence for disputes                     | Internal notes, audit log, status emails, published policy                                      |
| 18 | **Medium**   | Manual STL delivery (ADR-019): slow or forgotten sends; email attachment limits (~20–25 MB) below bundle size; the admin's drive is the only copy of the files | Delivery queue oldest-first; customer notified on send; compress or send a storage link for large bundles; owner backs up the drive |
| 9  | **Medium**   | Open reviews permit fake ratings that poison Top Rated                                  | Verified badge, one per user, moderation, rate limiting                                         |
| 10 | **Medium**   | Single payment provider; no fallback                                                    | Provider abstraction ready for a second adapter                                                 |
| 11 | **Medium**   | Unauthenticated guest uploads on a host co-locating database and inventory              | Content validation, re-encoding, scanning, quotas, private storage, retention                   |
| 12 | **Medium**   | Disk exhaustion corrupts the database                                                   | Retention policies, partitioning, disk alerting above 80%                                       |
| 14 | **Medium**   | No product variants; colour requests divert to WhatsApp                                 | Accepted limitation; monitor WhatsApp volume for reconsideration                                |
| 15 | **Low-Med**  | International demand may arrive before zones are enabled                                | WhatsApp quotation path; zone model already built                                               |
| 16 | **Low-Med**  | No caching or CDN                                                                       | Monitor; add when metrics justify                                                               |
| 17 | **Low**      | Account deletion versus record retention tension                                        | Anonymise rather than purge; block while orders open                                            |

---

## 30. Open Decisions

None block the start of development. Each should close before its module is built.

### 30.1 Awaiting Whish

| Item                                             | Impact                                                                                                                                                             |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Wallet-balance only, or general card acceptance? | **Determines whether the STL marketplace can serve customers outside Lebanon.** Their reply describes payment from a Whish balance; card acceptance is unconfirmed |
| Callback signature mechanism                     | Whether signature verification is active                                                                                                                           |
| Transaction status query API                     | Whether manual confirmation fallback is needed                                                                                                                     |
| Refund API or manual transfer                    | Refund workflow and admin burden                                                                                                                                   |
| Sandbox environment                              | Blocks integration testing, not design                                                                                                                             |
| USD support and settlement timeline              | Cash flow planning                                                                                                                                                 |
| 3D Secure and dispute process                    | Fraud exposure (largely moot if wallet-only)                                                                                                                       |
| Merchant eligibility documents                   | **May reveal that business registration is the real blocker**                                                                                                      |
| Fees and commission rates                        | Margin calculation on STL pricing                                                                                                                                  |

### 30.2 Awaiting Client

| Item                                | Impact                                               |
| ----------------------------------- | ---------------------------------------------------- |
| Domain registration                 | Blocks Whish application, email SPF/DKIM, deployment |
| STL delivery time promise           | Text shown on STL pages and at checkout (ADR-019)    |
| Transactional email provider        | Critical-path infrastructure                         |
| Courier partner and per-zone rates  | Data entry, not schema                               |
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

---

## 31. Future Roadmap

**Near term:** enable international shipping zones; courier API integration with tracking numbers; cash on delivery; customer invoice PDF download; abandoned-cart recovery; notification preferences and unsubscribe; bulk admin operations; tracking-number field.

**Medium term:** object storage migration with CDN; caching layer; second payment provider; product variants if WhatsApp volume justifies; 3D model preview for STL products; structured product Q&A; recommended print settings metadata; wishlist price-drop alerts; discount coupons; multi-admin roles.

**Long term:** mobile applications with push notifications; WhatsApp Business API for in-system tracking of manual orders; advanced analytics and reporting; commercial STL licensing; loyalty programme; gift cards; AI-assisted search and recommendations; additional languages; B2B enquiry path.

---

## 32. Glossary

| Term                      | Definition                                                                                   |
| ------------------------- | -------------------------------------------------------------------------------------------- |
| **Awaiting Delivery**     | State of a paid STL line until the administrator emails the file and marks it delivered      |
| **Batch Size**            | Units producible per lead-time cycle; drives dispatch estimation                             |
| **Bounded Context**       | A module owning its own tables and accessed only through service interfaces                  |
| **Bring Your Idea (BYI)** | The custom-printing lead workflow                                                            |
| **Idempotency Key**       | Client-supplied header preventing duplicate order or refund creation                         |
| **Kill Switch**           | Global setting pausing all new online checkouts                                              |
| **Lead Time**             | Days required to produce one batch of a physical product                                     |
| **Mixed Order**           | An order containing both digital and physical lines                                          |
| **Outbox**                | Table holding emails written inside a business transaction, delivered afterwards by a worker |
| **Projection**            | A derived value maintained from other state; order status is one                             |
| **Purchase Mode**         | Per-product setting: Online Only, WhatsApp Only, or Both                                     |
| **Shipping Zone**         | Named geographic area with a flat delivery rate                                              |
| **Snapshot**              | Immutable copy of a value captured at order time                                             |
| **STL Delivery Queue**    | Admin list of paid STL lines awaiting delivery, oldest first (ADR-019)                       |
| **Soft Delete**           | Marking a record deleted without removing it                                                 |
| **Verified Purchase**     | Review badge indicating a genuine purchase record exists                                     |
| **Whish**                 | Lebanese payment provider; Whish Pay is its merchant service                                 |

---

**End of Specification**

*This document is the single source of truth for Bekaa3D. Changes should be versioned, and material decisions recorded with their rationale so that context survives across sessions and across developers.*
