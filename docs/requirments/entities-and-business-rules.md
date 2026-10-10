# Entities and Business Rules — Bekaa3D

## Purpose

This document identifies the important Bekaa3D entities, their identities, relationships, lifecycles, invariants, transition rules, background processes, and deletion strategies.

The names used here are canonical and must match:

- Domain and application code
- Database tables and columns
- API resources
- Requirements
- Tests
- Documentation

## Enforcement labels

Each rule identifies where it should be protected:

- **[Domain]** — entity constructor, value object, or domain method
- **[DB]** — database constraint, unique index, foreign key, or check constraint
- **[Application]** — application service or use case
- **[Authorization]** — authentication and ownership policy
- **[Worker]** — scheduled or asynchronous process
- **[Infrastructure]** — payment, storage, email, proxy, or external adapter

---

# Identity Context

## Entity: User

**Identity:**
`user_id`

The same user remains the same entity even when their email, password, verification state, or personal information changes.

**Key attributes:**

- `id`
- `email`
- `password_hash`
- `email_verified_at`
- `role`
- `cash_payment_blocked_at` — set by a refused cash delivery or pickup no-show; cleared by an administrator (ADR-024)
- `anonymized_at`
- `deleted_at`
- `created_at`
- `updated_at`

**Lifecycle/status:**

```text
UNVERIFIED
  ├── VERIFIED
  └── PURGED

VERIFIED
  └── ANONYMIZED

ANONYMIZED
  └── terminal
```

The SRS does not require one `status` column. These states may be represented through `email_verified_at`, `anonymized_at`, and `deleted_at`.

**Relationships:**

- User `1:N` Address — User owns addresses
- User `1:N` Session — User owns sessions
- User `1:N` Order — User is the customer
- User `1:1` Cart — User owns one persistent cart
- User `1:N` Payment indirectly through Orders
- User `1:N` Offer — User submits negotiations
- User `1:N` Review — User authors reviews
- User `1:N` WishlistItem — User owns wishlist entries
- User `1:N` Notification — User receives notifications
- User `0:N` AuditLog — User may be the actor

**Rules:**

- **[DB]** Active user email addresses must be unique.
- **[Domain]** Registration requires an email address and password.
- **[Application]** Registration creates an unverified user.
- **[Authorization]** Unverified users may browse but cannot perform protected write actions.
- **[Authorization]** Cart, checkout, offer, review, and wishlist operations require email verification.
- **[Domain]** Passwords are stored only as Argon2id hashes.
- **[Application]** Verification and password-reset tokens must be single-use and expire.
- **[Application]** Changing the password revokes existing sessions.
- **[Authorization]** A user may access only their own private resources unless they are an administrator.
- **[Application]** Account deletion anonymizes personal information instead of deleting financial and delivery records.
- **[Application]** Anonymization is blocked while the user has open orders or unsettled refunds.
- **[Worker]** Accounts that remain unverified beyond the configured period are purged.
- **[Application]** A user with `cash_payment_blocked_at` set is offered only online payment; Ordering sets it through an Identity port, and only an administrator clears it.

**Transition rules:**

- `UNVERIFIED → VERIFIED`
  - Triggered by a valid, unused verification token.
  - Performed by the user.
  - Side effects: verification timestamp recorded and audit event written.

- `UNVERIFIED → PURGED`
  - Triggered after the configured unverified-account retention period.
  - Performed by a scheduled worker.
  - Allowed only if the account was never verified.

- `VERIFIED → ANONYMIZED`
  - Triggered by an eligible account-deletion request.
  - Performed by the account owner.
  - Blocked by open orders or unsettled refunds.
  - Side effects: login disabled, sessions revoked, personal information removed, retained records disconnected from direct identity.

**Deletion strategy:**
**Anonymize** verified customer accounts because financial, order, refund, and STL delivery history must be retained. Never-verified accounts may be purged after the configured retention period.

---

## Entity: Address

**Identity:**
`address_id`

**Key attributes:**

- `id`
- `user_id`
- `label`
- `recipient_name`
- `phone`
- `governorate`
- `city`
- `area`
- `street`
- `landmark_notes`
- `is_default`
- `deleted_at`

**Lifecycle/status:**
None.

Default selection is a property, not a lifecycle state.

**Relationships:**

- User `1:N` Address — required owner
- Address `0:N` Order — referenced only when selected at checkout
- Order stores an immutable address snapshot rather than depending on the live Address record

**Rules:**

- **[Authorization]** Only the owner may create, update, view, or remove an address.
- **[DB/Application]** A user may have multiple addresses but only one effective default.
- **[Domain]** Lebanese landmark notes are supported as a functional address field.
- **[Application]** Delivery checkout requires a valid address.
- **[Application]** Pickup and digital-only checkout do not require an address.
- **[Domain]** The address phone is a Lebanese number; it is the courier's contact and is snapshotted onto delivery Orders.
- **[Application]** Editing an Address must not change an existing Order’s address snapshot.

**Deletion strategy:**
**Soft delete**, because previous order snapshots and operational history must remain valid.

---

# Catalogue Context

## Entity: Product

**Identity:**
`product_id`

**Key attributes:**

- `id`
- `product_type`
- `category_id`
- `name`
- `description`
- `slug`
- `seo_title`
- `seo_description`
- `price_cents`
- `currency`
- `is_visible`
- `is_featured`
- `is_available` (both types; SRS §6.1)
- `deleted_at`
- Physical-only:
  - `purchase_mode`
  - `material_id`
  - `colour_id`
  - `dimensions`
  - `lead_time_days`
  - `batch_size`
  - `max_quantity_per_line`

- Maintained aggregates:
  - `average_rating`
  - `review_count`

**Lifecycle/status:**

Product does not require one combined status field. It has separate state dimensions:

```text
Visibility:
HIDDEN ↔ VISIBLE

Availability:
AVAILABLE ↔ UNAVAILABLE

Record lifecycle:
ACTIVE → SOFT_DELETED
```

Visibility, availability, and deletion must remain separate concepts.

**Relationships:**

- Product `N:1` Category — required
- Product `0:1` Material — required for physical products
- Product `0:1` Colour — required for physical products
- Product `1:N` ProductImage
- Product `1:N` CartItem
- Product `1:N` OrderItem
- Product `1:N` Review
- Product `1:N` WishlistItem
- STL Product `1:N` Offer

**Rules:**

- **[DB]** A product must be either physical or STL.
- **[DB]** An STL product cannot carry physical-only fields.
- **[DB]** A physical product must contain all required physical-product fields.
- **[Domain]** Prices use integer cents and an explicit currency code.
- **[Domain]** All V1 prices use USD.
- **[Domain]** Product name is required.
- **[DB]** Slug must be unique among non-deleted records.
- **[Application]** Search indexing uses the `english` text-search configuration.
- **[Domain]** A physical product has exactly one purchase mode:
  - `online_only`
  - `whatsapp_only`
  - `both`

- **[Domain]** Physical products are made on demand and have no stock quantity.
- **[Domain]** `lead_time_days`, `batch_size`, and `max_quantity_per_line` must be positive.
- **[Application]** An unavailable product remains visible but cannot be added to the cart.
- **[Application]** A hidden or soft-deleted product does not appear in storefront queries.
- **[Application]** A WhatsApp-only product bypasses cart and checkout.
- **[Application]** Purchase mode and availability are revalidated during checkout.
- **[Application]** Product changes must not change historical OrderItem snapshots.
- **[Application]** Rating aggregates are recalculated after review creation, edit, moderation, or deletion.

**Transition rules:**

- `VISIBLE → HIDDEN`
  - Administrator only.
  - Side effect: product disappears from public catalogue queries.

- `AVAILABLE → UNAVAILABLE`
  - Administrator only.
  - Side effect: product remains visible but cannot be added or checked out.

- `ACTIVE → SOFT_DELETED`
  - Administrator only.
  - Side effects: product disappears from active catalogue queries and its slug is released for reuse.

**Deletion strategy:**
**Soft delete**, because order history, reviews, offers, and analytics may still reference the product.

---

# Ordering Context

## Entity: Cart

**Identity:**
`cart_id`

One persistent Cart belongs to one User.

**Key attributes:**

- `id`
- `user_id`
- `created_at`
- `updated_at`

**Lifecycle/status:**
None.

The Cart persists across sessions and becomes empty after successful checkout.

**Relationships:**

- User `1:1` Cart — User owns Cart
- Cart `1:N` CartItem — Cart owns items

**Rules:**

- **[DB]** At most one active Cart per User.
- **[Authorization]** Only the owning verified customer may read or modify the Cart.
- **[Domain]** A Cart may contain physical and STL products simultaneously.
- **[Application]** Checkout locks the Cart before validation.
- **[Application]** Checkout clears the Cart only after Order creation succeeds.
- **[Application]** A failed checkout leaves the Cart unchanged.
- **[Application]** Cart contents never prove that a Product remains purchasable; all items are revalidated at checkout.

**Deletion strategy:**
The Cart is normally retained and cleared. If removal is needed, use **soft delete**.

---

## Entity: CartItem

**Identity:**
`cart_item_id`

Business uniqueness is:

```text
(cart_id, product_id)
```

**Key attributes:**

- `id`
- `cart_id`
- `product_id`
- `quantity`
- `price_snapshot_cents`
- `currency`
- `created_at`
- `updated_at`

**Lifecycle/status:**
None.

**Relationships:**

- Cart `1:N` CartItem — Cart owns item
- Product `1:N` CartItem — required reference

**Rules:**

- **[DB]** A Cart may contain at most one CartItem for a given Product.
- **[Application]** Adding an existing Product merges quantities.
- **[DB]** STL quantity must equal exactly one.
- **[Application]** An STL the User already owns (a paid, unrefunded digital OrderItem) cannot be added as an STL CartItem.
- **[Domain]** Physical quantity must be between one and the current product maximum.
- **[Application]** Hidden, deleted, unavailable, or WhatsApp-only products cannot be added.
- **[Domain]** Price is snapshotted when the Product is added.
- **[Application]** Price changes are detected and presented for explicit confirmation during checkout.
- **[DB/Application]** Concurrent additions of the same Product must result in one row with a valid final quantity.

**Deletion strategy:**
Removed or consumed CartItems may be **soft deleted** according to the global deletion convention.

---

## Entity: Order

**Identity:**
`order_id`

`order_number` is the human-readable business identifier but is not the database identity.

**Key attributes:**

- `id`
- `order_number`
- `user_id`
- `source`
- `status`
- `fulfillment_method`
- `payment_method` — `online` or `cash`, chosen at checkout (ADR-024)
- `subtotal_cents`
- `tax_cents`
- `total_cents`
- `currency`
- `address_snapshot`
- `customer_email_snapshot` — the verified account email at checkout; STL files are emailed here (ADR-019)
- `contact_phone_snapshot` — every physical Order; from the address for delivery, entered at checkout for pickup
- `customer_note`
- `internal_admin_note`
- `estimated_dispatch_at`
- `terms_accepted_at`
- `cash_terms_accepted_at` — cash orders only (ADR-024)
- `placed_at`
- lifecycle timestamps

**Lifecycle/status:**

Order status is a **derived projection** and must never be assigned directly.

```text
Online Order, payment pending or processing
  └── PENDING_PAYMENT

Online Order, payment failed or expired
  └── CANCELLED

Cash Order, no Payment yet
  ├── all items cancelled         → CANCELLED
  └── otherwise                   → IN_PROGRESS

Payment paid (online or cash)
  ├── all items cancelled         → CANCELLED
  ├── all items refunded          → REFUNDED
  ├── any refund present          → PARTIALLY_REFUNDED
  ├── no physical items           → COMPLETED
  ├── all physical items terminal → COMPLETED
  └── otherwise                   → IN_PROGRESS
```

This is a projection rule rather than a normal command-driven state machine. A derived `payment_due` flag marks an unpaid cash Order.

**Relationships:**

- User `1:N` Order — User owns Orders
- Order `1:N` OrderItem — Order owns items
- Order `1:N` Payment — historical online attempts, or one cash Payment created at handover; one live at most
- Order `1:N` Refund
- Order `1:N` OrderStatusHistory
- Order `0:1` IdempotencyRecord for checkout response
- Order `0:1` Offer as source when created through accepted-offer checkout

**Rules:**

- **[Domain]** An Order contains at least one OrderItem.
- **[Domain]** Money uses integer cents and explicit currency.
- **[Application]** Subtotal and total are recomputed server-side. The platform charges no shipping; the courier collects the delivery fee (ADR-024).
- **[Domain]** `total = subtotal + tax`.
- **[Domain]** Tax equals zero in V1.
- **[Domain]** Order and OrderItem snapshots are immutable after placement.
- **[Application]** Delivery Orders require an address snapshot.
- **[Application]** Pickup Orders require no delivery address.
- **[DB]** Every Order with a fulfillment method has a contact phone snapshot.
- **[Application]** `payment_method = cash` requires every OrderItem to be physical, cash enabled, the customer not blocked, fewer than `cash_max_open_orders` open unpaid cash Orders, and a total within `cash_max_order_total`; checked under the cart lock. OrderItems are inserted once with the Order, so no later change can add an STL item to a cash Order.
- **[Application]** A cash Order has no checkout hold and no Payment until the cash handover.
- **[Application]** Digital-only Orders have no fulfillment method.
- **[Application]** The estimated dispatch date considers all physical items, quantities, lead times, and batch sizes.
- **[Application]** Checkout requires a verified customer and idempotency key.
- **[Authorization]** Only the owner or an administrator may view private Order details.
- **[Authorization]** Customers may cancel only eligible physical items while every physical item is `pending`.
- **[Application]** WhatsApp-only transactions do not create an Order.
- **[Application]** Order status is recomputed in the same transaction as Payment or OrderItem changes.

**Transition rules:**

Order transitions occur indirectly through:

- Payment changes
- OrderItem fulfillment changes
- Cancellation
- Refunds
- STL delivery (an administrator marking a digital item delivered)
- Cash handover (an administrator recording the cash for a cash Order)

No API or administrator action may directly execute:

```text
order.status = requested_status
```

**Deletion strategy:**
Orders are **retained**, not deleted through business workflows. Cancellation and refunds are business states. If an administrative deletion mechanism ever exists, it must use soft deletion and preserve financial history.

---

## Entity: OrderItem

**Identity:**
`order_item_id`

**Key attributes:**

- `id`
- `order_id`
- `product_id`
- `product_type`
- translated name snapshots
- image snapshot
- `unit_price_cents`
- `quantity`
- `line_total_cents`
- `fulfillment_status`
- physical production snapshots
- `receipt_confirmed_at`, `problem_reported_at` — optional customer feedback after delivery or pickup (ADR-024)
- `offer_id`
- lifecycle timestamps

**Lifecycle/status:**

### Digital OrderItem

```text
PENDING
  └── AWAITING_DELIVERY
        ├── DELIVERED
        │     └── REFUNDED
        └── REFUNDED
```

`AWAITING_DELIVERY` is entered atomically with Payment verification. `DELIVERED` is set by an administrator after emailing the file, recording `delivered_at` and the acting administrator (ADR-019).

### Physical OrderItem — Delivery

```text
PENDING                                  (received)
  ├── IN_PRODUCTION                      (start printing; internal)
  │     ├── READY_TO_SHIP                (finished)
  │     │     ├── SHIPPED
  │     │     │     ├── DELIVERED
  │     │     │     │     └── REFUNDED   (paid only)
  │     │     │     └── RETURNED
  │     │     │           ├── SHIPPED
  │     │     │           ├── IN_PRODUCTION
  │     │     │           ├── REFUNDED   (paid only)
  │     │     │           └── CANCELLED  (unpaid cash only)
  │     │     └── CANCELLED
  │     └── CANCELLED
  └── CANCELLED
```

### Physical OrderItem — Pickup

```text
PENDING
  ├── IN_PRODUCTION
  │     ├── READY_FOR_PICKUP
  │     │     ├── PICKED_UP
  │     │     │     └── REFUNDED   (paid only)
  │     │     └── CANCELLED        (no-show)
  │     └── CANCELLED
  └── CANCELLED
```

`IN_PRODUCTION` is internal: the customer sees it as received and is not notified. On a cash Order, `DELIVERED` and `PICKED_UP` are reached only through the cash handover (ADR-024).

**Relationships:**

- Order `1:N` OrderItem — Order owns items
- Product `1:N` OrderItem — historical reference
- OrderItem `0:1` Offer — when negotiated
- OrderItem `0:N` RefundItem

**Rules:**

- **[Domain]** `line_total = unit_price × quantity`.
- **[DB]** STL quantity must equal one.
- **[Domain]** Snapshots are immutable after Order placement.
- **[Application]** Digital items enter `awaiting_delivery` only after independent Payment verification, and only an item in `awaiting_delivery` can be marked `delivered`.
- **[DB]** At most one paid, unrefunded digital OrderItem exists per User and STL Product (ownership, INV-18).
- **[Application]** A digital item refunded while `awaiting_delivery` leaves the STL delivery queue and must not be sent.
- **[Application]** Marking a digital item delivered notifies the customer in-app and by email, and is audit-logged.
- **[Application]** Digital fulfillment is independent of physical fulfillment in a Mixed Order.
- **[Application]** Start printing (`pending → in_production`) closes customer self-cancellation; it sends no customer email or notification.
- **[Application]** The customer is emailed and notified at `ready_to_ship`, `shipped`, `ready_for_pickup`, and `delivered` / `picked_up`.
- **[Application]** Cancelling a paid item creates a refund obligation; cancelling an unpaid cash item creates none. A cash `returned → cancelled` or `ready_for_pickup → cancelled` blocks the customer from cash.
- **[Application]** Receipt confirmation and problem reports never change an item's state.
- **[Authorization]** Only administrators may perform fulfillment transitions.
- **[Application]** Customers may cancel only owned physical items still in `pending`.
- **[Application]** Invalid or skipped transitions are rejected.
- **[Application]** Status history, audit entries, notifications, and Order projection updates are created with transitions.
- **[DB/Application]** Cancellation racing start printing must lock the same item so only one transition succeeds.
- **[Domain]** `returned` is not terminal.

**Deletion strategy:**
OrderItems are **retained permanently** as part of the financial and fulfillment record.

---

# Payments Context

## Entity: Payment

**Identity:**
`payment_id`

The payment provider’s transaction identifier is an external reference, not the internal identity.

**Key attributes:**

- `id`
- `order_id`
- `provider`
- `provider_transaction_id`
- `status`
- `amount_cents`
- `currency`
- `initiated_at`
- `confirmed_at`
- `recorded_by` — the administrator who recorded a cash Payment
- `failed_at`
- `expired_at`
- verification metadata

**Lifecycle/status:**

```text
PENDING
  ├── PROCESSING
  │     ├── PAID
  │     │     ├── PARTIALLY_REFUNDED
  │     │     │     └── REFUNDED
  │     │     └── REFUNDED
  │     ├── FAILED
  │     └── EXPIRED
  └── EXPIRED
```

A cash Payment (`provider = cash`) is created directly as `PAID` by the cash handover and never passes through `PENDING` or `PROCESSING`; it may then be refunded (ADR-024).

**Relationships:**

- Order `1:N` Payment — historical attempts
- Payment `1:N` WebhookEvent
- Payment `1:N` Refund

**Rules:**

- **[DB]** At most one live Payment may exist per Order.
- **[Domain]** An online Payment amount and currency must match the Order total; a cash Payment must equal the sum of the Order's live item totals.
- **[Application]** A cash Payment is created only by the administrator's cash handover, in the same transaction that marks every live item delivered or picked up; no callback, webhook or job can create one.
- **[Application]** A callback is a notification, never proof of payment.
- **[Application]** `paid` is reachable only after independent server-side verification or permitted manual confirmation.
- **[Application]** Underpayment must never produce `paid`.
- **[DB]** Duplicate provider events must not apply a Payment result twice.
- **[Application]** External provider queries occur without holding database locks.
- **[Application]** Applying a verified result updates Payment, digital items (to `awaiting_delivery`), physical items, Order projection, offer state, audit history, and email outbox atomically.
- **[Worker]** Online Payments stuck in processing are reconciled every fifteen minutes.
- **[Application]** A new Payment attempt is permitted only after the previous live attempt fails or expires.
- **[Authorization]** Only authorized administrators may perform manual confirmation.

**Transition rules:**

- `PENDING → PROCESSING`
  - Payment-provider flow started.

- `PROCESSING → PAID`
  - Only after amount, currency, and provider status are independently confirmed.
  - Side effects include digital items entering `awaiting_delivery` and physical fulfillment activation.

- `PENDING|PROCESSING → EXPIRED`
  - Triggered when the checkout or payment hold period expires.

- `PROCESSING → FAILED`
  - Triggered by a confirmed provider failure.

- `PAID → PARTIALLY_REFUNDED|REFUNDED`
  - Triggered by settled refund amounts.

**Deletion strategy:**
**Retain permanently.** Payment records are financial and audit evidence.

---

## Entity: WebhookEvent

**Identity:**
`webhook_event_id`

Business uniqueness is:

```text
(provider, provider_event_id)
```

**Key attributes:**

- `id`
- `provider`
- `provider_event_id`
- `payment_id`
- received payload
- signature-verification result
- `received_at`
- processing metadata

**Lifecycle/status:**
The SRS does not prescribe an exact status enum.

Minimum semantic processing stages are:

```text
RECEIVED
  └── PROCESSED

RECEIVED
  └── REJECTED
```

Exact enum names require an implementation decision.

**Relationships:**

- Payment `1:N` WebhookEvent
- Payment Provider `1:N` external events

**Rules:**

- **[DB]** `(provider, provider_event_id)` must be unique.
- **[Infrastructure]** Provider signature is verified where supported.
- **[Application]** The raw event is persisted before expensive processing.
- **[Application]** Duplicate delivery returns success without applying business effects twice.
- **[Application]** Receiving an event does not mark a Payment paid.
- **[Application]** Invalid signatures trigger rejection and alerting.
- **[Application]** The callback endpoint responds quickly to prevent provider retries caused by timeout.

**Deletion strategy:**
**Retain** according to payment and audit retention policy. Do not hard-delete events needed to prove callback history.

---

## Entity: Refund

**Identity:**
`refund_id`

**Key attributes:**

- `id`
- `order_id`
- `payment_id`
- `amount_cents`
- `currency`
- `reason`
- `requested_by`
- `approved_by`
- `method`
- `settlement_state`
- `created_at`
- `settled_at`

**Lifecycle/status:**

The SRS explicitly requires a pending obligation that remains open until settlement.

```text
PENDING
  └── SETTLED
```

The SRS does not define additional terminal statuses. States such as `failed` or `cancelled` must not be introduced without a documented decision.

**Relationships:**

- Order `1:N` Refund
- Payment `1:N` Refund
- Refund `1:N` RefundItem
- RefundItem `N:1` OrderItem
- Refunds have no shipping component (ADR-024)

**Rules:**

- **[Domain]** Refund amount must be positive.
- **[DB]** Refund money uses integer cents and an explicit currency.
- **[Application]** Total refunds cannot exceed the remaining refundable Payment amount.
- **[Application]** Refunds may cover selected OrderItems.
- **[Application]** A cash Payment is refunded only after its handover, always with method `manual`, up to the cash recorded.
- **[Application]** Refunding a digital item marks it `refunded`; one still awaiting delivery leaves the delivery queue.
- **[Application]** A pending Refund remains visible in the administrator obligations queue until settlement.
- **[Application]** If the online provider does not support refund APIs, settlement is recorded after manual transfer.
- **[Application]** Refund requests use idempotency protection.
- **[Authorization]** Only authorized administrators may issue Refunds.
- **[DB/Application]** Concurrent refunds must lock or recheck the remaining refundable balance.
- **[Application]** A confirmed chargeback also marks affected digital items `refunded`.

**Transition rules:**

- `PENDING → SETTLED`
  - Performed after provider or manual-transfer confirmation.
  - Side effects: Payment status and Order projection recalculated.

**Deletion strategy:**
**Retain permanently.** Refunds represent financial obligations and settlement evidence.

---

# Digital Assets Context

Removed by ADR-019. The platform stores no STL files, so AssetVersion, StlAsset, Entitlement, Download and DownloadStatsMonthly do not exist. A customer owns an STL through a paid, unrefunded digital OrderItem, and delivery state lives on that OrderItem (see *Digital OrderItem*, Fulfillment).

---

# Negotiation Context

## Entity: Offer

**Identity:**
`offer_id`

**Key attributes:**

- `id`
- `user_id`
- `product_id`
- `status`
- `turn`
- `responds_by`
- `agreed_price_cents`
- `checkout_expires_at`
- rejection cooldown metadata
- `created_at`
- `updated_at`

**Lifecycle/status:**

```text
AWAITING_ADMIN
  ├── AWAITING_CUSTOMER
  ├── ACCEPTED
  ├── REJECTED
  ├── WITHDRAWN
  └── EXPIRED

AWAITING_CUSTOMER
  ├── AWAITING_ADMIN
  ├── ACCEPTED
  ├── WITHDRAWN
  └── EXPIRED

ACCEPTED
  ├── PAID
  ├── CHECKOUT_EXPIRED
  └── AUTO_CLOSED
```

**Relationships:**

- User `1:N` Offer — User owns Offer
- STL Product `1:N` Offer
- Offer `1:N` OfferRound — Offer owns append-only history
- Offer `0:1` Order

**Rules:**

- **[Domain]** Offers apply only to STL Products.
- **[DB]** At most one live Offer exists per User and Product.
- **[Application]** A customer who already owns the Product cannot open an Offer.
- **[Application]** Initial amounts below the configured minimum percentage are rejected.
- **[Application]** Offer submission is rate-limited.
- **[Application]** Rejection creates or resets a cooldown.
- **[Domain]** Only the party whose turn it is may counter or respond.
- **[Application]** Each counter switches the turn and resets `responds_by`.
- **[Domain]** Acceptance freezes the agreed price permanently.
- **[Application]** Acceptance creates a customer- and product-specific one-time checkout.
- **[Application]** After acceptance, the response timer no longer applies; only checkout expiration applies.
- **[Application]** Acquisition through another route auto-closes the live Offer.
- **[Application]** Complete OfferRound history is retained permanently.
- **[DB/Application]** Concurrent Offer creation relies on the database live-offer constraint.

**Transition rules:**

- `AWAITING_ADMIN ↔ AWAITING_CUSTOMER`
  - Caused by counter-offers.
  - Side effects: OfferRound appended, turn changed, deadline reset.

- `AWAITING_* → ACCEPTED`
  - Performed by the current responding party.
  - Side effects: price frozen and one-time checkout issued.

- `AWAITING_* → EXPIRED`
  - Performed by scheduled expiry worker when `responds_by` passes.

- `ACCEPTED → PAID`
  - Triggered by independently verified payment.

- `ACCEPTED → CHECKOUT_EXPIRED`
  - Performed when the one-time checkout period passes.

- `ACCEPTED → AUTO_CLOSED`
  - Triggered when the customer acquires the Product through another route.

**Deletion strategy:**
**Status only.** Offers and OfferRounds are retained permanently.

---

# Engagement Context

## Entity: Review

**Identity:**
`review_id`

Business uniqueness is:

```text
(user_id, product_id) among active reviews
```

**Key attributes:**

- `id`
- `user_id`
- `product_id`
- `rating`
- review text
- verified-purchase indicator or derived value
- `hidden_at`
- `deleted_at`
- `created_at`
- `updated_at`

**Lifecycle/status:**

```text
VISIBLE
  └── HIDDEN

HIDDEN
  └── VISIBLE
```

The state may be represented through `hidden_at` instead of a status enum.

**Relationships:**

- User `1:N` Review
- Product `1:N` Review

**Rules:**

- **[Authorization]** Only verified users may create or edit Reviews.
- **[DB]** One active Review exists per User and Product.
- **[DB]** Rating is an integer from one through five.
- **[Application]** Purchase is not required to create a Review.
- **[Application]** Verified Purchase status derives from qualifying purchase evidence.
- **[Application]** Badge is recomputed when a purchase is paid (online verification or cash handover) or refunded. An unpaid or refused cash purchase never earns it.
- **[Application]** WhatsApp-only purchases cannot produce a Verified Purchase badge because no platform purchase record exists.
- **[Authorization]** Users may edit only their own Review.
- **[Authorization]** Administrators may hide or restore Reviews.
- **[Application]** Links, profanity, and abusive submission rates are filtered.
- **[Application]** Rating aggregates are recalculated after creation, update, moderation, or deletion.

**Deletion strategy:**
Use **hide/restore and soft deletion**. Do not remove moderation or historical records physically.

---

## Entity: Notification

**Identity:**
`notification_id`

**Key attributes:**

- `id`
- `user_id`
- `type`
- `payload`
- `read_at`
- `created_at`

**Lifecycle/status:**

```text
UNREAD
  └── READ
```

The state may be represented by `read_at`.

**Relationships:**

- User `1:N` Notification

**Rules:**

- **[Authorization]** A user may view or mark only their own Notifications.
- **[Domain]** Notification type must be from a controlled set.
- **[Domain]** Payload uses JSON but must not contain unnecessary secrets or sensitive data.
- **[Application]** Notifications are created for supported payment, order, offer, STL-sent, refund, and account events.
- **[Application]** Marking a Notification read does not alter the underlying business entity.

**Deletion strategy:**
Retention is not numerically defined by the SRS. Use **soft deletion or retention-based pruning** after a formal retention decision.

---

## Entity: CustomRequest

**Identity:**
`custom_request_id`

**Key attributes:**

- `id`
- visitor name
- email
- phone
- project title
- description
- preferred material
- preferred colour
- dimensions
- `status`
- quoted amount
- outcome
- administrator notes
- `created_at`
- `updated_at`

**Lifecycle/status:**

```text
NEW
  └── CONTACTED
        ├── QUOTED
        │     ├── IN_PROGRESS
        │     │     └── COMPLETED
        │     │           └── CLOSED
        │     └── LOST
        └── LOST
```

**Relationships:**

- CustomRequest `1:N` CustomRequestAttachment
- User relationship is optional because guest submissions are allowed
- Administrator may be recorded as transition actor

**Rules:**

- **[Application]** Guest submission is allowed.
- **[Infrastructure]** Captcha must succeed.
- **[Application]** Per-IP and per-email rate limits apply.
- **[Domain]** Required contact and project fields must be valid.
- **[Infrastructure]** Attachments are validated by content, re-encoded, malware-scanned, and privately stored.
- **[Authorization]** Only administrators may view private attachments or change pipeline state.
- **[Application]** CustomRequest is a lead workflow and does not create an Order or Payment.
- **[Application]** Administrator may record a quoted amount and won/lost outcome.
- **[Application]** Pipeline transitions must follow the defined sequence.
- **[Worker]** Expired attachments are purged after the configured retention period.

**Transition rules:**

- `NEW → CONTACTED`
  - Administrator records first contact.

- `CONTACTED → QUOTED`
  - Administrator records quotation details.

- `CONTACTED|QUOTED → LOST`
  - Administrator records the lead as lost.

- `QUOTED → IN_PROGRESS`
  - Work begins after an off-platform agreement.

- `IN_PROGRESS → COMPLETED → CLOSED`
  - Administrator records completion and final closure.

**Deletion strategy:**
CustomRequest records use **soft deletion or status retention**. Attachments are **hard-purged** after their configured retention period because the SRS explicitly requires physical removal.

---

## Entity: ContactMessage

**Identity:**
`contact_message_id`

**Key attributes:**

- `id`
- visitor name
- email
- phone
- subject
- message
- `status`
- `created_at`
- `updated_at`

**Lifecycle/status:**

```text
NEW
  └── READ
        └── REPLIED
              └── ARCHIVED
```

**Relationships:**

- User relationship is optional because guest submission is allowed
- Order `0:N` ContactMessage — a signed-in customer's problem report links to the Order (ADR-024)
- Administrator actions may be represented in AuditLog

**Rules:**

- **[Infrastructure]** Public submission requires captcha.
- **[Application]** Public submission is rate-limited.
- **[Domain]** Contact information and message must be valid.
- **[Authorization]** Only administrators may read or transition messages.
- **[Application]** ContactMessage is not a CustomRequest, Order, Review, or Notification.
- **[Application]** Invalid state transitions are rejected.

**Deletion strategy:**
Use **archived status** for normal removal from active queues. Apply soft deletion only if an administrative deletion capability is required.

---

# Platform Context

## Entity: EmailOutbox

**Identity:**
`email_outbox_id`

**Key attributes:**

- `id`
- recipient
- template
- payload
- `send_after`
- attempt count
- last error
- sent timestamp
- creation timestamp

**Lifecycle/status:**

The SRS requires pending delivery, retries, successful delivery, and failure alerting, but does not prescribe an exact enum.

Minimum lifecycle:

```text
PENDING
  ├── SENT
  └── PENDING
        └── retry with increased attempt count
```

A terminal `FAILED` state may be introduced only through an explicit implementation decision defining retry limits and manual recovery.

**Relationships:**

- May reference User
- May reference originating Order, Payment, Refund, Offer, or account event
- Business entity does not own the Outbox record; it is written as part of the same transaction

**Rules:**

- **[Application]** Outbox record is inserted inside the business transaction that creates the email-triggering event.
- **[Worker]** Pending records are processed every minute.
- **[Worker]** Failed sends use exponential backoff.
- **[Worker]** Repeated failures trigger an operational alert.
- **[Application]** Email-provider failure must never roll back Payment, Order, or fulfillment changes.
- **[DB/Worker]** Concurrent workers must not deliver the same record simultaneously.

**Deletion strategy:**
Retention is not specified. Retain delivery history according to a formally approved operational-retention policy; use **retention-based pruning**, not ad hoc deletion.

---

## Entity: Setting

**Identity:**
`setting_id` or a unique typed setting key

**Key attributes:**

- `id`
- `key`
- `value`
- value type
- validation metadata
- `updated_by`
- `updated_at`

**Lifecycle/status:**
None.

**Relationships:**

- User `0:N` Setting updates as administrator actor
- Setting changes `1:N` AuditLog entries

**Rules:**

- **[DB]** Setting key must be unique.
- **[Domain]** Value must conform to the declared type.
- **[Application]** Value must satisfy key-specific validation rules.
- **[Authorization]** Only administrators may change settings.
- **[Application]** Every change records old value, new value, actor, and timestamp.
- **[Application]** Operational business parameters are Settings rather than source-code constants.
- **[Application]** The accepting-orders kill switch blocks new checkout but does not interrupt in-flight Payments.

Required settings include:

- Accepting-orders kill switch
- Offer-response window
- Offer-checkout window
- Rejection cooldown
- Minimum-offer percentage
- Checkout hold period
- Unverified-account purge period
- Cash payment switch, maximum open cash Orders per customer, maximum cash Order total (ADR-024)
- Pickup address and hours
- WhatsApp number

**Deletion strategy:**
Normally **not deleted**. Obsolete settings should be retired through migration or soft deletion while preserving audit history.

---

## Entity: IdempotencyRecord

**Identity:**
`idempotency_record_id`

Business lookup identity should include the operation scope and supplied key.

**Key attributes:**

- `id`
- operation scope
- actor or user identifier
- idempotency key
- request-body fingerprint
- stored response
- response status
- created timestamp
- expiration timestamp if adopted

**Lifecycle/status:**
None required.

**Relationships:**

- May reference User
- May reference Order
- May reference Refund

**Rules:**

- **[DB]** Key must be unique within its operation and actor scope.
- **[Application]** Repeating a key with the same request body returns the original response.
- **[Application]** Reusing a key with a different body returns conflict.
- **[Application]** The response is recorded only for a committed operation.
- **[Application]** Checkout and Refund creation require idempotency.
- **[DB/Application]** Concurrent identical requests must create one business result.

**Deletion strategy:**
Retention duration is not specified by the SRS. Use **time-based pruning** only after defining a period long enough to cover client retries and payment workflows.

---

## Entity: AuditLog

**Identity:**
`audit_log_id`

**Key attributes:**

- `id`
- actor type
- actor ID
- action
- entity type
- entity ID
- previous state
- new state
- metadata
- correlation ID
- `created_at`

**Lifecycle/status:**
None.

AuditLog is append-only.

**Relationships:**

- May reference any important business entity
- User relationship is optional because System or external events may be actors

**Rules:**

- **[Application]** Administrator actions are audit-logged.
- **[Application]** Authentication events are audit-logged.
- **[Application]** Payment changes and STL deliveries are audit-logged.
- **[Application]** Important status transitions are audit-logged.
- **[Domain]** Existing entries cannot be edited through business APIs.
- **[Application]** Sensitive information and secrets must be excluded or redacted.
- **[Infrastructure]** Audit data is partitioned monthly.
- **[Worker]** Records remain hot for 24 months and are then archived.

**Deletion strategy:**
**Append-only retention and archive.** Do not hard-delete through normal application operations.

---

# Supporting Entities

These entities remain part of the domain model but generally do not require a full independent aggregate workflow.

| Entity                  | Identity                           | Important rules                                                                                          |
| ----------------------- | ---------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Session                 | `session_id`                       | Belongs to one User; refresh token stored hashed; rotates on use; revoked on password change             |
| VerificationToken       | `verification_token_id`            | Single-use, short-lived, stored hashed, belongs to one User                                              |
| PasswordResetToken      | `password_reset_token_id`          | Single-use, short-lived, stored hashed, belongs to one User                                              |
| ProductImage            | `product_image_id`                 | Belongs to one Product; supports order and cover selection; file/database consistency must be reconciled |
| Category                | `category_id`                      | Cannot be deleted while assigned to Products; owns its own name and slug                                 |
| Material                | `material_id`                      | Administrator-managed controlled value, not free text                                                    |
| Colour                  | `colour_id`                        | Administrator-managed controlled value, not free text                                                    |
| OrderStatusHistory      | `history_id`                       | Append-only record of Order projection or item-state changes                                             |
| RefundItem              | `refund_item_id`                   | Allocates part of a Refund to an OrderItem                                                               |
| OfferRound              | `offer_round_id`                   | Append-only sequence within an Offer; records actor, action, amount, message, timestamp                  |
| WishlistItem            | `wishlist_item_id`                 | Unique User–Product association; verified User only                                                      |
| CustomRequestAttachment | `attachment_id`                    | Private, validated, re-encoded, scanned, expiring file                                                   |

---

# Aggregate Boundaries

Recommended aggregate roots:

| Aggregate root | Controlled entities                             |
| -------------- | ----------------------------------------------- |
| User           | Address, Session, verification and reset tokens |
| Product        | ProductImage                                    |
| Cart           | CartItem                                        |
| Order          | OrderItem, OrderStatusHistory                   |
| Payment        | WebhookEvent                                    |
| Refund         | RefundItem                                      |
| Offer          | OfferRound                                      |
| CustomRequest  | CustomRequestAttachment                         |
| Review         | Its moderation and rating contribution          |
| Setting        | Its typed value and validation                  |

Cross-aggregate operations such as payment verification must be coordinated by an application service and committed transactionally where required.

---

# Status-Machine Coverage Checklist

Entities with an explicit or semantic status lifecycle:

| Entity               |   State machine defined? | Notes                                               |
| -------------------- | -----------------------: | --------------------------------------------------- |
| User                 |                      Yes | Unverified, verified, anonymized, purge             |
| Product              | Yes, separate dimensions | Visibility, availability, deletion are not one enum |
| Order                |                      Yes | Derived projection; never directly assigned         |
| OrderItem — digital  |                      Yes | Pending, awaiting delivery, delivered, refunded     |
| OrderItem — delivery |                      Yes | Printing, shipping, return, cash refusal, refund    |
| OrderItem — pickup   |                      Yes | Printing, pickup, no-show, refund                   |
| Payment              |                      Yes | Pending through paid, failure, expiry, refund       |
| WebhookEvent         |      Partially specified | Exact enum requires implementation decision         |
| Refund               |             Yes, minimum | SRS specifies pending obligation until settled      |
| Offer                |                      Yes | Full negotiation and checkout lifecycle             |
| Review               |            Yes, semantic | Visible and hidden                                  |
| Notification         |            Yes, semantic | Unread and read                                     |
| CustomRequest        |                      Yes | New through closed or lost                          |
| ContactMessage       |                      Yes | New, read, replied, archived                        |
| EmailOutbox          |      Partially specified | Exact retry/failure enum requires decision          |

No additional status values should be added without defining:

1. Who may execute the transition
2. Required preconditions
3. Database and concurrency protection
4. Side effects
5. Failure and retry behavior
6. Whether the state is terminal
7. How the transition is tested
