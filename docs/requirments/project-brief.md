# Project Brief — Bekaa3D

> This brief summarizes the business case behind the SRS. Where it conflicts with
> [`docs/SRS.md`](../SRS.md), the SRS wins — that document is the single source of truth.

## Project Classification

**Category:** Complex transactional commerce platform
**Profile:** C — Complex backend

**Reason:**

Bekaa3D is a production dual-commerce platform that sells both made-to-order physical products and STL files, which the administrator emails to buyers after payment (ADR-019).

The backend handles online payments, cash on delivery for physical-only orders (ADR-024), payment webhooks, independently verified transactions, mixed orders, per-line fulfillment, partial refunds, an STL delivery queue, offer negotiations, full-text search, user-generated uploads, audit logging, and several reliability-critical background jobs.

Its classification is driven by transactional and operational complexity rather than traffic volume. Payment verification, refunds, checkout idempotency, concurrency races, file security, and recovery procedures must remain correct even when the number of users is relatively small.

**Current deliberate exclusions:**

- No microservices; bounded contexts remain within a modular monolith
- No Kubernetes
- No multi-region deployment
- No active-active or automatic failover
- No object storage or CDN in V1
- No dedicated external search engine
- No second online payment provider in V1, unless SRS §30.4 chooses both Whish and a card gateway
- No courier API integration
- No international shipping
- No platform-charged shipping; the courier prices and collects delivery (ADR-024)
- No mobile applications
- No product variants
- No tax or VAT calculation
- No event-streaming platform such as Kafka

**Required Profile C components:**

- Clean Architecture with domain, application, infrastructure, and API layers
- Repository abstractions for domain aggregates
- PostgreSQL constraints protecting business invariants
- Redis for queues, rate limits, and appropriate short-lived coordination
- Background workers and scheduled jobs
- Transactional email outbox with retries
- Idempotency for checkout, refunds, and payment callbacks
- Independent server-side payment verification
- Payment reconciliation for missed callbacks
- Structured logging, audit logging, monitoring, and alerting
- Malware scanning and secure upload processing
- Automated backups with restoration verification
- Staging environment and CI/CD with rollback support
- Unit, integration, contract, end-to-end, concurrency, and security testing

**Upgrade triggers:**

- Concurrent usage consistently approaches or exceeds the 200-user target
- Catalogue size approaches or exceeds 10,000 products
- Local file storage creates disk-capacity or backup problems
- The 99% availability target becomes insufficient for the business
- A single server becomes an unacceptable point of failure
- PostgreSQL full-text and trigram search no longer meet search-quality or latency targets
- Online-provider outages or business requirements justify a second payment provider
- Cash-on-delivery refusals make the cash option unprofitable (ADR-024)
- Manual STL delivery becomes a bottleneck and automated delivery is reconsidered (ADR-019)
- Background-job volume requires independently scalable worker pools
- Multiple development teams need independent ownership and deployment cycles
- Operational complexity justifies container orchestration
- International shipping, courier tracking, mobile applications, or multi-vendor selling enter the confirmed scope

**Architecture boundary:**

Profile C does not automatically mean microservices or Kubernetes. Bekaa3D should begin as a modular monolith deployed through Docker Compose, with clear bounded contexts and infrastructure abstractions. More distributed infrastructure should be introduced only when measured operational or organizational pressure justifies it.

---

## Problem

Bekaa3D currently lacks a unified platform for selling both made-to-order physical 3D-printed products and STL files. Customers need a trustworthy storefront where they can discover products, pay online, negotiate STL prices, track physical orders, and know when their purchased STL files have been sent.

The business administrator needs one operational system for managing products, payments, fulfillment, STL deliveries, refunds, customer requests, offers, notifications, and analytics without accessing the database directly.

## Today's Process

Based on the business context documented in the SRS, the current process is primarily relationship-based and handled through WhatsApp and manual communication.

Customers contact the business to ask about products, custom printing, prices, payment, production, and delivery. The administrator manually follows conversations, confirms payments, coordinates production and delivery, handles customer updates, and manages custom-printing requests.

WhatsApp will remain an intentional sales channel in V1, but online orders, STL purchases and their delivery records, payment verification, and fulfillment records will be managed through the platform.

## Cost of the Status Quo

**Numeric baseline:** not supplied in the SRS.

The following measurements must be collected before or during early development:

- Administrator hours spent handling orders each week
- Median time required to confirm a payment
- Missed or duplicated orders per month
- Customer enquiries that receive no response
- Refund obligations that remain unresolved
- Custom-printing leads lost before receiving a quotation
- Time spent manually sending files and order updates
- Customer disputes caused by missing payment, delivery, or fulfillment records

A four-week baseline should be recorded before production launch so post-launch improvement can be measured.

## Success Metrics

The project is successful when:

- 100% of online payments are independently verified server-side before manufacturing begins or an STL is sent.
- A verified customer can complete the STL journey — discovery, checkout and payment — and is notified when the administrator has emailed the file; the administrator sees every STL still owed in one queue (ADR-019).
- A verified customer can complete a physical-product order and follow it through delivery or workshop pickup.
- 100% of V1 administrative operations can be completed through the dashboard without direct database access.
- Catalogue endpoints respond in less than 500 ms at p95.
- Search responds in less than 800 ms at p95.
- Checkout completes in less than 2 seconds, excluding the payment-provider redirect.
- The platform supports 200 concurrent users without degradation.
- Monthly availability is at least 99%.
- The catalogue supports 10,000 products without index redesign.

The SRS defines the core business success criteria as permanent STL access, trackable physical orders, continued WhatsApp accessibility, complete dashboard operation, and independently verified payments.

## Users and Roles

### Visitor

**Can:**
- Browse and search the catalogue
- View products and reviews
- Submit a Bring Your Idea request
- Submit a contact message
- Open a product-specific WhatsApp conversation

**Cannot:**
- Use the cart
- Purchase products
- Submit offers, reviews, or wishlist changes

### Registered but unverified user

Can browse as a visitor but cannot perform protected write actions until email verification is completed.

### Verified customer

**Can:**
- Manage profile and addresses
- Use the cart and checkout
- Purchase physical and STL products
- See whether each purchased STL has been sent
- Submit and respond to offers
- Track orders
- Cancel eligible physical orders
- Write reviews
- Manage a wishlist
- Read notifications
- Export personal data
- Request account deletion

### Administrator

**Can:**
- Manage the catalogue
- Upload product images
- Work the STL delivery queue: email purchased files and mark them sent
- Manage orders and fulfillment
- Verify payments when manual confirmation is required
- Issue and track refunds
- Manage offers
- Moderate reviews
- Process Bring Your Idea requests
- Manage settings and users
- View audit records and analytics

### System

**Performs:**
- Email delivery and retries
- Checkout expiration
- Offer expiration
- Payment reconciliation
- Attachment cleanup
- Backup verification
- Partition maintenance
- Notification and projection updates

### Payment provider — undecided

External system responsible for online payment processing, callbacks, and transaction-status queries where supported. Whish, a card gateway, or both are being considered (SRS §30.4, ADR-024).

### Courier

External to the platform. The courier sets and collects the delivery fee and collects the cash for cash-on-delivery orders. The courier is not a system user, and V1 contains no courier API integration.

The authentication and role boundaries are explicitly defined in the SRS.

## Scope — Version 1

### In scope

- English-language public storefront
- Physical-product catalogue
- STL digital marketplace
- Per-product purchase modes: Online only, WhatsApp only, Both
- Full-text search
- Typo-tolerant search and autocomplete
- Faceted filters and sorting
- Registration, authentication, and email verification
- Customer profiles and saved addresses
- Mixed cart containing physical and digital products
- Idempotent checkout
- Courier delivery and workshop-pickup fulfillment
- Online payment integration (provider undecided, SRS §30.4)
- Cash on delivery and cash at pickup for physical-only orders (ADR-024)
- Payment webhook handling
- Independent payment verification
- Payment reconciliation
- Manual payment-confirmation fallback
- Physical-order fulfillment workflow
- Per-line order statuses
- Customer and administrator cancellation
- Full and partial per-line refunds
- Refund-obligation tracking
- STL delivery queue with manual email delivery (ADR-019)
- STL offer and counter-offer negotiation
- Reviews and verified-purchase badges
- Wishlist
- In-app notifications
- Transactional email
- Bring Your Idea lead workflow
- Contact-message workflow
- Admin dashboard
- Operational settings
- Audit logging
- Business analytics
- Data export
- Account anonymization
- Rate limiting
- Captcha
- Malware scanning
- Monitoring and verified backups

### Out of scope — Version 1

The following exclusions are deliberate and should not be added without a formal scope decision:

- Product variants selectable during checkout
- Colour, material, or dimension customization during checkout
- International shipping
- Courier API integration
- Live courier tracking
- Shipping zones, shipping fees and shipping refunds (ADR-024)
- Guest checkout
- Product comments separate from reviews
- Online payment for Bring Your Idea requests
- Automated quotation for custom-printing requests
- STL licensing management
- Multi-vendor marketplace support
- Seller onboarding or seller payouts
- Mobile applications
- Tax or VAT calculation
- Inventory quantity management for physical products
- Automated physical-production scheduling
- Microservices
- Kubernetes
- Multi-region deployment
- Active-active failover
- External search engines such as Elasticsearch
- Object storage and CDN delivery in the initial release
- Multiple online payment providers, unless SRS §30.4 chooses both Whish and a card gateway
- WhatsApp Business API integration
- Loyalty points
- Gift cards
- Discount coupons
- AI recommendations

The original SRS explicitly excluded product variants, international shipping, courier integration, cash on delivery (moved into V1 by ADR-024), guest checkout, comments, Bring Your Idea payment, STL licensing, mobile applications, and tax calculation.

## Constraints

### Team

- Three-person development team
- Responsibilities must be divided by bounded context or delivery phase
- The project should remain a modular monolith to avoid unnecessary distributed-system overhead

### Budget

- Previously discussed target: approximately USD 3,000
- Negotiable lower limit: approximately USD 2,500
- This is a severe constraint for a Profile C system and requires strict scope control and phased delivery

### Market and operations

- Primary market: Lebanon
- Prices are stored and charged in USD
- Physical products are made on demand
- Physical fulfillment is manually managed
- Workshop pickup and Lebanese courier delivery are supported; the courier prices delivery
- Customers may pay physical-only orders in cash on delivery or at pickup
- WhatsApp remains an important purchasing and communication path
- V1 has one primary administrator

### Technology

- Python 3.13
- FastAPI
- Pydantic v2
- SQLAlchemy 2 async
- Alembic
- PostgreSQL 16
- Redis
- arq workers and scheduled jobs
- nginx
- ClamAV
- Docker Compose
- Single-VPS deployment for V1

The SRS requires Clean Architecture with domain, application, infrastructure, and API layers, organized as bounded contexts within one backend.

### Payment integration

- The online provider is undecided: Whish, a card gateway, or both (SRS §30.4), due before VS-032
- Merchant credentials are required for live online payment
- Webhook-signature support, status-query support, refunds, rate limits, sandbox availability, and settlement behavior depend on the chosen provider
- Nothing may be produced or sent solely because a callback was received
- Cash is recorded only by the administrator at handover, in the same action that marks the order delivered or picked up

### Hosting and reliability

- V1 runs on a single VPS
- The single server is an acknowledged availability limitation
- PostgreSQL data, private files, uploads, backups, and logs require active disk monitoring
- Off-server encrypted backups are mandatory
- A staging environment is required before enabling live payments

### Language and accessibility

- English only at launch; no localization or RTL support
- Product names are required
- WCAG 2.1 AA is the accessibility target

### Security and legal

- Personally identifiable information must be protected and excluded from logs
- Payment, authentication, STL delivery, upload, and administrator actions must be audited
- Uploaded content must be validated, re-encoded where applicable, malware-scanned, and stored privately
- Terms, privacy, refund policy, invoicing requirements, and damaged-goods policy must be approved before launch
- The SRS does not identify a named regulatory compliance regime

## Deadline and Milestones

**Calendar deadline:** Not specified in the SRS.

The delivery milestone is a phased V1 release:

| Phase | Contents | Blocked by provider? |
| --- | --- | --- |
| **0 — Foundation** | Database, authentication, verification, admin foundation, catalogue, search, settings, outbox, and job infrastructure | No |
| **1 — Storefront** | Public pages, reviews, wishlist, notifications, Bring Your Idea, contact, and WhatsApp paths | No |
| **2 — Commerce** | Cart, checkout, orders, fulfillment, delivery, pickup, cash on delivery, cancellation, and refunds using a mock payment provider | No |
| **3 — Digital** | STL delivery queue and offers | No |
| **4 — Live payments** | Online provider integration, callbacks, independent verification, reconciliation, and manual-confirmation fallback | **Yes** |
| **5 — Hardening** | Rate limits, captcha, malware scanning, MFA, monitoring, backup drill, data rights, and load testing | No |

Production launch must not occur before Phase 4 and Phase 5 acceptance. Only the live-payment phase is blocked by the provider decision and credentials.
