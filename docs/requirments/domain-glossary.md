# Domain Glossary — Bekaa3D

This glossary defines the canonical vocabulary for Bekaa3D.

The same terms must be used consistently in:

* Requirements and acceptance criteria
* Python classes, functions, variables, and enums
* Database tables and columns
* API endpoints and response fields
* Tests, logs, documentation, and team discussions

A synonym must not be introduced when a canonical term already exists.

| Term                            | Means                                                                                                                                                                          | Does NOT mean / confused with                                           |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------- |
| **Visitor**                     | A person using the public storefront without an authenticated account.                                                                                                         | Registered User, Verified Customer, Administrator                       |
| **User**                        | The persisted account entity containing identity, authentication, verification, and account-state information.                                                                 | Customer role, Visitor, Administrator role                              |
| **Registered User**             | A user account that has been created but whose email may not yet be verified.                                                                                                  | Automatically a Verified Customer                                       |
| **Unverified User**             | A registered user whose email has not been verified and who therefore cannot perform protected write actions.                                                                  | Visitor; the user has an account and may authenticate                   |
| **Verified Customer**           | A user with a verified email who may use customer features such as cart, checkout, offers, reviews, and wishlist.                                                   | Every User; Administrator                                               |
| **Administrator**               | An authorized user who operates catalogue, orders, payments, refunds, offers, moderation, settings, and analytics.                                                             | Customer, System, database operator                                     |
| **System**                      | Automated application behavior such as scheduled jobs, projections, expiration, reconciliation, and notifications.                                                             | Administrator or external service                                       |
| **Payment Provider**            | An external service that processes money and exposes payment creation, callback, status-query, and possibly refund capabilities.                                               | Payment record, Order, Webhook Event                                    |
| **Whish**                       | The payment provider used by Bekaa3D in V1.                                                                                                                                    | A Payment, wallet balance, or internal Bekaa3D service                  |
| **Courier**                     | An external party responsible for physically transporting an order to a customer.                                                                                              | System user, Fulfillment Method, Shipping Zone                          |
| **Catalogue**                   | The searchable public collection of physical and STL products.                                                                                                                 | Inventory, Cart, Admin product editor                                   |
| **Product**                     | A sellable catalogue item shared by both physical and STL product types.                                                                                                       | Order Item, Cart Item                                                   |
| **Physical Product**            | A made-to-order product that requires production and may be delivered or collected from the workshop.                                                                          | Stocked inventory item, STL Product                                     |
| **STL Product**                 | A digital product whose files the administrator emails to the customer after payment (ADR-019).                                                                                           | Individual STL File, Physical Product                                   |
| **Product Type**                | The permanent classification of a product as physical or STL.                                                                                                                  | Purchase Mode, Category                                                 |
| **Category**                    | An administrator-managed grouping used to organize and filter products.                                                                                                        | Product Type, Material, subcategory                                     |
| **Material**                    | An administrator-managed reference value describing the material of a physical product.                                                                                        | Customer-selectable product variant                                     |
| **Colour**                      | An administrator-managed reference value describing the displayed colour of a physical product.                                                                                | Customer-selectable product variant                                     |
| **Product Variant**             | A selectable variation such as colour, material, or dimensions during purchase. Product variants are excluded from V1.                                                         | Product attribute displayed in the catalogue                            |
| **Slug**                        | The URL identifier for a product or other catalogue resource.                                                                                                                  | Database primary key, product name                                      |
| **Visibility**                  | Whether a product may appear in the public storefront.                                                                                                                         | Availability, Purchase Mode                                             |
| **Availability**                | Whether a visible product is temporarily eligible to be added to the cart and purchased.                                                                                       | Visibility, physical stock quantity                                     |
| **Featured Product**            | A product selected by the administrator for highlighted storefront placement.                                                                                                  | Best-selling or automatically top-rated product                         |
| **Purchase Mode**               | The configured way a physical product may be purchased: Online Only, WhatsApp Only, or Both.                                                                                   | Fulfillment Method, Payment Method, Product Type                        |
| **Online Only**                 | A purchase mode requiring the product to be purchased through the Bekaa3D checkout.                                                                                            | Delivery only                                                           |
| **WhatsApp Only**               | A purchase mode where the complete commercial transaction occurs outside the platform through WhatsApp.                                                                        | An online order with WhatsApp notifications                             |
| **Both**                        | A purchase mode allowing either platform checkout or an off-platform WhatsApp conversation.                                                                                    | Mixed Order                                                             |
| **Cart**                        | The verified customer’s persistent collection of products being considered for checkout.                                                                                       | Order, Wishlist, Payment                                                |
| **Cart Item**                   | One product selection inside a cart, including quantity and the price observed when it was added.                                                                              | Order Item, Product                                                     |
| **Price Snapshot**              | The recorded product price at a specific business moment, such as cart addition or order placement.                                                                            | Current catalogue price                                                 |
| **Checkout**                    | The transactional process that validates a cart and creates an order, order items, consent record, and pending payment.                                                        | Payment verification, Order fulfillment                                 |
| **Idempotency Key**             | A client-supplied identifier ensuring that repeating the same protected request does not create a duplicate result.                                                            | Order number, payment-provider event ID                                 |
| **Order**                       | The commercial record created from a successful checkout or accepted-offer checkout, containing monetary totals, customer snapshots, fulfillment information, and order items. | Cart, Payment, Shipment                                                 |
| **Order Number**                | The human-readable identifier used by customers and administrators to reference an order.                                                                                      | Database primary key, Idempotency Key                                   |
| **Order Source**                | The workflow that created an order, such as cart checkout or accepted-offer checkout.                                                                                          | Marketing source or payment provider                                    |
| **Order Item**                  | A purchased product line inside an order with immutable product, price, quantity, and fulfillment snapshots.                                                                   | Cart Item, Product, Shipment                                            |
| **Physical Order Item**         | An order item representing a physical product and carrying production and fulfillment state.                                                                                   | Entire Order, Digital Order Item                                        |
| **Digital Order Item**          | An order item representing an STL product and carrying its delivery state (awaiting delivery, delivered, refunded).                                                            | STL File                                                                |
| **Mixed Order**                 | An order containing at least one physical order item and at least one digital order item.                                                                                      | A product with both purchase modes                                      |
| **Order Status**                | A derived projection calculated from payment state and order-item states.                                                                                                      | A value directly selected by an administrator                           |
| **Order-Item Status**           | The individual fulfillment or digital-delivery state of one order item.                                                                                                        | Order Status, Payment Status                                            |
| **Projection**                  | A value derived and maintained from authoritative underlying records. Order Status is a projection.                                                                            | Independent source of truth                                             |
| **Snapshot**                    | An immutable copy of business data captured at a specific moment, especially order placement.                                                                                  | Live reference that changes with catalogue edits                        |
| **Customer Note**               | Information submitted by the customer for the order.                                                                                                                           | Internal Admin Note                                                     |
| **Internal Admin Note**         | Operational information visible only to administrators.                                                                                                                        | Customer-visible status message                                         |
| **Fulfillment**                 | The operational process of producing and handing over physical order items, and of emailing purchased STL files (STL Delivery).                                                | Payment, Checkout                                                       |
| **Fulfillment Method**          | The selected handover method for physical order items: Delivery or Pickup.                                                                                                     | Purchase Mode, Payment Method                                           |
| **Delivery**                    | A fulfillment method in which a physical product is transported to a customer address.                                                                                         | Dispatch, Shipment record, Pickup                                       |
| **Pickup**                      | A fulfillment method in which the customer collects a paid physical product from the workshop.                                                                                 | Cash on delivery, Delivery                                              |
| **Delivery Address**            | A customer-managed address that may be selected for a delivery checkout.                                                                                                       | Order Address Snapshot                                                  |
| **Address Snapshot**            | The immutable address copied onto an order at checkout.                                                                                                                        | A saved address that changes when the customer edits their address book |
| **Shipping Zone**               | An administrator-managed Lebanese geographic area with a configured flat delivery fee.                                                                                         | Courier route, address, international shipping region                   |
| **Shipping Fee**                | The monetary charge calculated from the selected shipping zone and snapshotted onto the order.                                                                                 | Product price, tax, courier payment                                     |
| **Lead Time**                   | The number of days required to produce one batch of a physical product.                                                                                                        | Estimated delivery time                                                 |
| **Batch Size**                  | The number of units that can be produced within one lead-time cycle.                                                                                                           | Maximum quantity per order                                              |
| **Maximum Quantity per Line**   | The greatest physical-product quantity allowed in one cart or order line.                                                                                                      | Batch Size, stock level                                                 |
| **Estimated Dispatch Date**     | The estimated date by which all physical items should be ready to leave the workshop.                                                                                          | Guaranteed delivery date                                                |
| **Dispatch**                    | The event of a physical order becoming ready to leave or actually leaving the workshop.                                                                                        | Delivery to the customer                                                |
| **Production**                  | The manufacturing work performed for a paid physical order item.                                                                                                               | Order creation or payment processing                                    |
| **Cancellation**                | Stopping an eligible order item before completion, subject to the production cutoff and refund rules.                                                                          | Refund settlement                                                       |
| **Production Cutoff**           | The transition into `in_production`, after which customers can no longer self-cancel.                                                                                          | Checkout expiration or payment expiration                               |
| **Return**                      | A physical item that comes back after shipment or delivery failure and requires re-shipment, reprinting, or refund resolution.                                                 | Refund, Cancellation                                                    |
| **Payment**                     | The internal record of a money-processing attempt associated with an order.                                                                                                    | Order, provider callback, proof of successful payment                   |
| **Payment Attempt**             | One attempt to collect the order total through the payment provider. Only one live attempt may exist per order.                                                                | Customer retry request after an active attempt                          |
| **Payment Status**              | The lifecycle state of a payment, such as pending, processing, paid, failed, expired, partially refunded, or refunded.                                                         | Order Status                                                            |
| **Pending Payment**             | A payment created but not yet completed or independently confirmed.                                                                                                            | Unpaid cart                                                             |
| **Paid**                        | A payment state reached only after independent server-side confirmation of provider status and amount.                                                                         | Callback received                                                       |
| **Payment Callback**            | A notification sent by the payment provider indicating that a payment event may have occurred.                                                                                 | Proof of payment                                                        |
| **Webhook Event**               | The persisted representation of a callback received from an external provider.                                                                                                 | Payment record or Payment Confirmation                                  |
| **Webhook Signature**           | Provider-supplied cryptographic evidence that a callback was sent by the provider, where supported.                                                                            | Independent payment-status verification                                 |
| **Payment Verification**        | The server-side process of querying or otherwise independently confirming provider status, currency, and amount.                                                               | Trusting callback contents                                              |
| **Manual Payment Confirmation** | An administrator-confirmed payment based on checking the provider dashboard when automated status verification is unavailable.                                                 | Arbitrary administrator override                                        |
| **Payment Reconciliation**      | A scheduled process that checks payments stuck in processing and resolves missed callbacks.                                                                                    | Accounting reconciliation of all business revenue                       |
| **Live Payment**                | A payment in pending, processing, or paid state that prevents another active attempt for the same order.                                                                       | Any historical failed or expired payment                                |
| **Refund**                      | A record representing money that must be returned for specified order items, shipping, or both.                                                                                | Cancellation, Chargeback, store credit                                  |
| **Refund Item**                 | The portion of a refund allocated to a specific order item or shipping component.                                                                                              | Order Item                                                              |
| **Refund Obligation**           | A tracked duty to return money that remains open until settlement is confirmed.                                                                                                | Completed refund transfer                                               |
| **Refund Settlement**           | Confirmation that the customer has actually received the refunded amount.                                                                                                      | Creation or approval of a refund record                                 |
| **Partial Refund**              | A refund covering less than the complete paid order amount.                                                                                                                    | Partial payment                                                         |
| **Chargeback**                  | A payment reversal initiated through the payment provider or financial channel.                                                                                                | Administrator-issued Refund                                             |
| **STL Delivery**                | The administrator emailing a paid STL's files from their own drive and marking the digital order item delivered (ADR-019).                                                       | Download, automatic delivery                                            |
| **Awaiting Delivery**           | The state of a paid digital order item whose files the administrator has not yet emailed.                                                                                      | Pending payment                                                         |
| **STL Delivery Queue**          | The administrator's list of digital order items awaiting delivery, oldest first.                                                                                               | Order queue for physical fulfillment                                    |
| **STL Ownership**               | A customer holding a paid, unrefunded digital order item for an STL product; blocks a repeat purchase and earns the Verified Purchase badge.                                    | Entitlement (removed by ADR-019), wishlist entry                        |
| **Offer**                       | A customer-specific negotiation for the price of one STL product.                                                                                                              | Coupon, general discount, physical-product negotiation                  |
| **Live Offer**                  | An offer currently awaiting a party’s response or accepted but still within its checkout window.                                                                               | Rejected, withdrawn, expired, or paid offer                             |
| **Offer Round**                 | One immutable action in an offer negotiation, such as submit, counter, accept, reject, or withdraw.                                                                            | Entire Offer                                                            |
| **Counter-Offer**               | A new proposed price that switches the negotiation turn to the other party.                                                                                                    | Editing a previous Offer Round                                          |
| **Offer Turn**                  | The party currently required to respond: customer or administrator.                                                                                                            | User role or workflow owner                                             |
| **Offer Response Deadline**     | The time by which the party holding the current turn must respond.                                                                                                             | Accepted-offer checkout deadline                                        |
| **Accepted Offer**              | An offer whose negotiated price has been frozen and for which a one-time checkout is available.                                                                                | Completed purchase                                                      |
| **Offer Checkout**              | A customer- and product-specific checkout created from an accepted offer at the agreed price.                                                                                  | Normal cart checkout                                                    |
| **Offer Checkout Window**       | The period during which an accepted offer may be purchased.                                                                                                                    | Offer Response Deadline                                                 |
| **Offer Cooldown**              | The waiting period after rejection before the customer may submit another offer for the same STL product.                                                                      | Rate limit                                                              |
| **Review**                      | A customer-authored rating and text assessment of a product.                                                                                                                   | Product Comment, Contact Message                                        |
| **Product Comment**             | A conversational product discussion feature, deliberately excluded from V1.                                                                                                    | Review                                                                  |
| **Rating**                      | An integer score from one through five belonging to a Review.                                                                                                                  | Product aggregate rating                                                |
| **Rating Aggregate**            | The maintained average rating and review count for a product.                                                                                                                  | Individual Review                                                       |
| **Verified Purchase**           | A review badge showing that the reviewer has qualifying purchase evidence.                                                                                                     | Identity verification or email verification                             |
| **Review Moderation**           | An administrator action that hides or restores a review without deleting its history.                                                                                          | Editing customer review content                                         |
| **Wishlist**                    | A verified customer’s saved collection of products of interest.                                                                                                                | Cart or purchased STLs                                                  |
| **Wishlist Item**               | One association between a customer and a wished-for product.                                                                                                                   | Cart Item                                                               |
| **Notification**                | An in-application message informing a user of a business event.                                                                                                                | Email Outbox record                                                     |
| **Email**                       | A customer-facing message delivered through the transactional email provider.                                                                                                  | In-app Notification                                                     |
| **Email Outbox**                | The database-backed queue of email messages written inside business transactions and delivered asynchronously.                                                                 | Sent-email history or Notification                                      |
| **Outbox Message**              | One pending, sent, retrying, or failed email-delivery record in the Email Outbox.                                                                                              | Domain event                                                            |
| **Bring Your Idea (BYI)**       | The custom-printing lead workflow through which visitors submit ideas and reference images for manual evaluation.                                                              | Product order, automated quotation, online purchase                     |
| **Custom Request**              | One Bring Your Idea submission and its business-processing state.                                                                                                              | Contact Message, Order                                                  |
| **Custom Request Attachment**   | A privately stored reference image submitted with a Custom Request.                                                                                                            | Product Image or STL File                                               |
| **Quote**                       | An administrator-recorded proposed amount for a Custom Request handled outside platform checkout.                                                                              | Offer, Order total, automated price                                     |
| **Contact Message**             | A general visitor enquiry submitted through the contact form.                                                                                                                  | Custom Request, Review, Notification                                    |
| **Lead**                        | A potential custom-printing customer represented by a Custom Request.                                                                                                          | Verified Customer or completed Order                                    |
| **Pipeline**                    | The ordered business states through which a Custom Request or operational record moves.                                                                                        | Background-job queue                                                    |
| **Setting**                     | A typed, administrator-editable business parameter that can change without deployment.                                                                                         | Source-code constant or environment secret                              |
| **Kill Switch**                 | The global Setting that blocks new online checkouts while allowing payments already in progress to continue.                                                                   | Application shutdown or maintenance mode                                |
| **Audit Log**                   | An append-only record of significant administrator, authentication, payment, STL delivery, and state-transition actions.                                                        | Application log or Order Status History                                 |
| **Status History**              | The ordered history of state changes for a particular business entity.                                                                                                         | Current status or general Audit Log                                     |
| **Application Log**             | Operational diagnostic output used to understand application behavior and failures.                                                                                            | Audit Log                                                               |
| **Soft Delete**                 | Marking a record as deleted while retaining it in storage and excluding it from normal active queries.                                                                         | Physical database deletion or anonymization                             |
| **Anonymization**               | Removing or replacing personal data while retaining necessary financial and operational records.                                                                               | Soft Delete or complete erasure                                         |
| **Data Export**                 | A customer-requested JSON package containing the customer’s supported account and activity data.                                                                               | Database backup                                                         |
| **Retention Period**            | The configured duration for keeping a category of data before pruning, anonymizing, or archiving it.                                                                           | Session lifetime or timeout                                             |
| **Background Job**              | Work executed outside an API request, including email delivery, expiration, reconciliation, cleanup, and backup checks.                                                        | Domain operation that must commit synchronously                         |
| **Scheduled Job**               | A Background Job started according to a defined cadence.                                                                                                                       | User-triggered API operation                                            |
| **Rate Limit**                  | A restriction on how frequently an actor may perform an action within a period.                                                                                                | Offer Cooldown                                                          |
| **Captcha**                     | A public-form anti-abuse verification mechanism.                                                                                                                               | Email verification or authentication                                    |
| **Storage Provider**            | The infrastructure abstraction responsible for private and public file persistence.                                                                                            | Database repository                                                     |
| **Payment Provider Port**       | The application-facing interface for creating, querying, verifying, and refunding provider payments.                                                                           | Whish-specific implementation                                           |
| **Repository**                  | An application interface responsible for loading and persisting domain aggregates.                                                                                             | Service, API router, generic utility module                             |
| **Bounded Context**             | A business module that owns its domain concepts and persistence and is accessed by other contexts through explicit interfaces.                                                 | Microservice or arbitrary folder                                        |
| **Aggregate**                   | A consistency boundary whose related changes are controlled through one domain entry point and transaction.                                                                    | Database table or bounded context                                       |
| **Invariant**                   | A business rule that must always remain true, including under concurrency and failure.                                                                                         | Input-validation preference                                             |
| **Domain Event**                | A record that a meaningful domain fact occurred, should domain-event handling later be introduced.                                                                             | Email Outbox Message, Webhook Event, Audit Log                          |
| **API Error Code**              | A stable machine-readable identifier describing an API failure.                                                                                                                | Translated human-readable message or HTTP status alone                  |

## Canonical naming rules

### 1. Use one canonical noun

Use:

* `Cart`, not basket or pending order
* `Order`, not sale, purchase record, or checkout
* `OrderItem`, not order product, detail, or line product
* `Payment`, not transaction when referring to the internal payment entity
* `Refund`, not reimbursement record
* `STL Delivery` / `awaiting_delivery`, not download, dispatch, or shipment for STL lines
* `Offer`, not bid, proposal, or discount request
* `CustomRequest`, not idea order or custom order
* `Notification`, not message when referring to the in-app notification entity

### 2. Keep roles separate from persisted entities

`User` is the persisted account entity.

`Verified Customer` and `Administrator` are roles or capabilities associated with a User. Do not create a separate Customer entity unless the domain model is deliberately changed.

Recommended examples:

```python
class User: ...


class UserRole(StrEnum):
    CUSTOMER = "customer"
    ADMIN = "admin"
```

Avoid:

```python
class User: ...


class Customer: ...


class AdminUser: ...
```

unless they truly become separate domain entities with different identity lifecycles.

### 3. Use product type and purchase mode correctly

```python
class ProductType(StrEnum):
    PHYSICAL = "physical"
    STL = "stl"


class PurchaseMode(StrEnum):
    ONLINE_ONLY = "online_only"
    WHATSAPP_ONLY = "whatsapp_only"
    BOTH = "both"
```

`ProductType` answers **what the product is**.

`PurchaseMode` answers **how a physical product may be purchased**.

`FulfillmentMethod` answers **how a physical order is handed to the customer**.

```python
class FulfillmentMethod(StrEnum):
    DELIVERY = "delivery"
    PICKUP = "pickup"
```

These three concepts must never share one enum or database column.

### 4. Distinguish current data from snapshots

Use explicit snapshot names on order records:

```text
product_name_snapshot
unit_price_cents
image_url_snapshot
shipping_zone_name_snapshot
shipping_fee_cents
address_snapshot
lead_time_days_snapshot
batch_size_snapshot
```

Do not name an immutable order-time value simply `product_name`, `price`, or `address` when it could be confused with current catalogue or profile data.

### 5. Distinguish order status from item status

Use:

```text
order.status
order_item.fulfillment_status
payment.status
refund.status
offer.status
```

Do not use one generic `status` value across contexts without the owning entity being clear.

An Order’s status is a derived projection. Order-item, Payment, Refund, and Offer statuses are their own authoritative state machines.

### 6. Distinguish callbacks from verification

Use:

```text
WebhookEvent
receive_webhook()
verify_payment()
reconcile_payment()
confirm_payment_manually()
```

Never name the webhook receiver:

```text
confirm_payment()
mark_as_paid()
complete_payment()
```

Receiving a callback does not confirm payment.

### 7. Distinguish ownership from delivery

Since ADR-019 there is no Entitlement or Download. A paid, unrefunded digital Order Item **is** STL ownership; its `fulfillment_status` (`awaiting_delivery`, `delivered`, `refunded`) is the delivery state. "Delivered" means the administrator emailed the file, not that the customer opened it.

### 8. Distinguish cancellation, refund, and return

* **Cancellation** stops eligible fulfillment.
* **Refund** records money to be returned.
* **Refund Settlement** confirms that money was returned.
* **Return** records a physical item coming back after shipment or delivery.

One action may lead to another, but they are not synonyms.

### 9. Use database names that match the glossary

Recommended table names:

```text
users
addresses
sessions
verification_tokens
password_reset_tokens

products
product_images
categories
materials
colours

carts
cart_items
orders
order_items
order_status_history

payments
webhook_events
refunds
refund_items

shipping_zones

offers
offer_rounds

reviews
wishlist_items
notifications
custom_requests
custom_request_attachments
contact_messages

settings
audit_logs
email_outbox
idempotency_records
```

Do not mix naming styles such as `order_details`, `payment_transactions`, `download_permissions`, or `idea_orders` unless the glossary is formally changed first.

### 10. Use API routes that expose the same vocabulary

Recommended route nouns:

```text
/products
/cart
/cart/items
/checkout
/orders
/orders/{order_id}/items
/payments
/payment-webhooks
/refunds
/stl-deliveries
/offers
/reviews
/wishlist
/notifications
/custom-requests
/contact-messages
/shipping-zones
/settings
/audit-logs
```

Avoid alternate route nouns such as:

```text
/basket
/sales
/purchases
/bids
/licenses
/files-owned
/idea-orders
```

### 11. Treat term changes as domain changes

Changing a canonical term requires updating:

* Glossary
* SRS and functional requirements
* Python domain and application names
* Database migrations
* API contracts
* Tests
* Documentation
* Analytics labels

A term must not be renamed in only one layer.
