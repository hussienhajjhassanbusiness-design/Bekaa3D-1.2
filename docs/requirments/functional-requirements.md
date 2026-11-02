Functional Requirements
General rules applying to all requirements
Public reads do not require authentication unless the resource is private.
Customer write actions require an authenticated, email-verified account.
Administrator functions require administrator authorization.
Resource access must verify ownership or administrator privileges.
Money must be represented as integer cents with an explicit currency.
Client-supplied prices and totals are never trusted.
Business operations affecting multiple records must run in a database transaction.
Errors must use stable machine-readable codes.
Protected operations must be auditable.
Conflicting operations must be resolved by database constraints, locking, idempotency, or explicit version checks rather than timing assumptions.

These invariants are required across ordering, payments, STL delivery, content, and authorization.

FR-01: Browse and search the catalogue

As a visitor,
I can browse and search physical and STL products,
so that I can discover products without creating an account.

Given:

The storefront is available

When:

The visitor opens a catalogue page
Applies filters or sorting
Enters a search query
Requests autocomplete suggestions

Then:

Only visible, non-deleted products belonging to active categories are returned
Physical and STL products can be viewed separately or together
Search covers product names and descriptions
Typo-tolerant matching is available
Filtering supports category, material, colour, price, rating, and product type
Results use cursor-based pagination
Product pages include images, descriptions, specifications, reviews, price, availability, and purchase mode

Negative cases:

Deleted or hidden products must not appear in storefront results
Products in inactive categories must not appear
An invalid cursor or unsupported sort field must be rejected
An unavailable product may be viewed but may not be purchased
A WhatsApp-only product may not be added to the cart

State transitions touched:

None for ordinary browsing
Product visibility changes affect whether the product appears in subsequent requests

Concurrent access:

New products or catalogue changes must not cause duplicate or missing records within a cursor-paginated result sequence
A product changed during browsing must be revalidated at checkout

Failure behaviour:

If full-text search produces too few results, trigram similarity is used as a fallback
If the database is unavailable, the API returns a structured service error rather than partial or stale unlabelled data

Traceability: F-004 through F-013.

FR-02: Register, verify, and authenticate an account

As a visitor,
I can register and verify my email,
so that I can use purchasing and engagement features.

Given:

The email is not already assigned to an active account
The password meets the configured password policy

When:

The visitor submits registration
Opens a valid verification link
Logs in or refreshes a session

Then:

An unverified account is created
A verification message is inserted into the transactional outbox
Verification activates protected write capabilities
Login creates short-lived access credentials and a rotating refresh session
Authentication credentials are delivered through secure HTTP-only cookies

Negative cases:

Duplicate active email addresses are not allowed
An unverified account cannot use the cart, checkout, offers, reviews, or wishlist
Expired, reused, or invalid verification and reset tokens are rejected
Authentication errors must not reveal whether an email exists
Suspended or anonymized accounts cannot log in

State transitions touched:

No account → unverified
Unverified → verified
Active session → revoked
Active account → anonymized

Concurrent access:

Concurrent registrations using the same email must result in one account at most
When the same refresh token is submitted concurrently, at most one rotation succeeds
Password changes revoke existing sessions

Failure behaviour:

Account creation and outbox insertion occur in the same transaction
Email-provider failure does not roll back account creation
Failed delivery is retried through the outbox worker
Never-verified accounts are purged after the configured period

Traceability: F-020 through F-024, F-130.

FR-03: View profile, manage addresses, export, and deletion

As a verified customer,
I can view my account profile and manage my saved addresses,
so that checkout and account information remain accurate.

Given:

The customer is authenticated and verified

When:

The customer views their account profile
Adds, updates, removes, or selects a default address
Requests a data export
Requests account deletion

Then:

The profile view returns the customer's account information (ID, email, verification/account state)
Multiple delivery addresses may be saved
A JSON export contains the customer’s profile, addresses, orders (with payment method and STL delivery records), reviews, offers, and the contact messages they sent while signed in (subject, message and date only; ADR-046)
Account deletion anonymizes personal data while retaining required financial and delivery records
Login is disabled after anonymization

Negative cases:

A customer cannot view another customer’s profile or modify another customer's address
Deletion is blocked while orders remain open or refunds remain unsettled
Financial and audit history must not be physically deleted through the customer endpoint
Invalid Lebanese address data must be rejected

State transitions touched:

Active account → anonymized
Address non-default → default
Previous default → non-default

Concurrent access:

Only one address may be treated as the default after a transaction commits
A deletion request racing an order or refund update must lock or recheck the account’s eligibility before anonymization

Failure behaviour:

Partial anonymization is prohibited
Export generation failure leaves the account unchanged and may be retried
Deletion and anonymization must roll back entirely if any required update fails

Traceability: F-024, F-025, F-034, F-035.

FR-04: Manage products and catalogue reference data

As an administrator,
I can create and manage products, images, categories, materials, and colours,
so that the storefront remains accurate.

Given:

The administrator is authenticated and authorized

When:

The administrator creates or edits a product
Changes visibility, availability, featured status, or purchase mode
Uploads or reorders images
Manages category, material, or colour records
Soft-deletes a product

Then:

Product data is validated according to physical or STL type
Product names are present
Slugs are unique among active records
Physical products contain required production fields
STL products do not contain physical-only fields
All changes are audit-logged

Negative cases:

Physical and STL fields may not be mixed illegally
A category assigned to products cannot be deleted
A duplicate active slug is rejected
Product records may not be hard-deleted
Non-administrators cannot access the management endpoints

State transitions touched:

Hidden ↔ visible
Available ↔ unavailable
Non-featured ↔ featured
Online only ↔ WhatsApp only ↔ both
Active → soft-deleted

Concurrent access:

A category deletion racing a product assignment must fail if the category becomes referenced
Unique constraints resolve simultaneous attempts to create the same slug
Conflicting administrator edits must not silently overwrite protected business fields; an optimistic version or equivalent conflict check should return a conflict response

Failure behaviour:

Database changes and audit records commit atomically
Failed file uploads do not leave a product referencing a missing image
Orphaned files are detected and removed by scheduled reconciliation

Traceability: F-110 through F-116.

FR-05: Maintain a mixed shopping cart

As a verified customer,
I can maintain a cart containing physical and STL products,
so that I can purchase both product types in one order.

Given:

The customer is authenticated and verified
The product is visible and eligible for online purchase

When:

The customer adds, updates, or removes a cart line

Then:

One persistent cart exists for the customer
Adding an existing product merges the quantity
STL quantity is always one
Physical quantity respects the configured per-line maximum
The price at the time of adding is recorded
The cart can contain physical and digital lines simultaneously

Negative cases:

WhatsApp-only products cannot be added
Hidden, deleted, or unavailable products cannot be added
An STL product already owned by the customer cannot be added
STL quantity greater than one is invalid
Physical quantity above the configured maximum is invalid

State transitions touched:

Empty cart → active cart
Active cart → updated cart
Active cart → empty cart

Concurrent access:

Concurrent additions of the same product must result in one cart line
Quantity merging must occur atomically
The final quantity may not exceed the product’s current cap

Failure behaviour:

A failed line update must not partially modify the cart
Ownership and product eligibility are checked again during checkout
A cart database constraint prevents duplicate product lines

Traceability: F-040, F-041.

FR-06: Create an idempotent checkout and order

As a verified customer,
I can submit my cart for checkout,
so that an order and payment attempt are created safely.

Given:

The customer has a non-empty cart
An idempotency key is supplied
The platform is accepting orders
Required delivery or pickup information is present, including a contact phone for pickup, and for an STL-only order on the `manual` provider (ADR-049)
A payment method is chosen: online (naming the provider when more than one is configured), or cash for an order whose every line is physical; either way, every line's product accepts it (BR-019)

When:

The customer submits checkout

Then:

The system locks the cart
Every product and quantity is revalidated
Current prices are compared with cart snapshots
Price changes require customer confirmation
Totals are recomputed server-side; no shipping amount is charged, because the courier collects the delivery fee
The payment method is validated against the recomputed total, never against a cart snapshot or client value
Order and order-line snapshots are created, including the payment method and contact phone
For an online order, a pending payment attempt is created with the chosen provider on the payment row; a cash order gets no payment until its cash handover
On the `manual` provider the response says the administrator will make contact (`next_step: await_admin_contact`, no redirect) and gives the hold deadline; the customer is notified, and every administrator alerted, in the order's transaction
Terms consent is recorded, including the cash terms for a cash order
Estimated dispatch is calculated for physical lines
The cart is cleared
The response is stored against the idempotency key

Negative cases:

WhatsApp-only, unavailable, hidden, or deleted products are rejected
Delivery without a valid address, or pickup without a contact phone, is rejected
An STL-only or offer checkout on the `manual` provider without a contact phone is rejected (CONTACT_PHONE_REQUIRED); any other provider refuses one there
A retry onto the `manual` provider of an order with no contact phone is rejected
A cart or offer checkout on the `manual` provider is rejected (MANUAL_ORDER_LIMIT_REACHED) while the customer already holds `manual_max_open_orders` unpaid `manual` orders (BR-150)
Cash is rejected for an order with any STL line, when cash is switched off, or when the customer or the normalised contact phone is blocked from cash
Cash is rejected when the customer or the contact phone already has the maximum number of unpaid cash orders, or the recomputed total is zero or exceeds the cash maximum
A payment method that any line's product does not accept is rejected, naming those products (cash for an online-only product, online for a cash-only product)
A cart whose lines share no accepted payment method (for example a cash-only product beside an online-only product or an STL) is rejected, and the customer is told to order them separately
An accepted-payment-methods change made after the order was placed never affects it, its payment retry or its handover
The same phone written in different formats is matched as one number (normalised, then keyed-hashed)
An unconfigured online provider is rejected
An already-owned STL is removed or rejected according to the checkout rule
A reused idempotency key with a different body returns a conflict
New checkout is rejected while the global accepting-orders switch is disabled
Client-supplied totals are ignored

State transitions touched:

Cart → cleared
No order → pending payment (online) or in progress (cash)
No payment → pending (online only)

Concurrent access:

Repeated checkout with the same key and body returns the original result
Two different keys submitted against the same cart must not create two valid orders
Cart locking and database constraints ensure only one checkout consumes the cart
The cart lock serialises one customer's checkouts, and a transaction-scoped advisory lock on the normalised contact phone serialises cash checkouts from different accounts sharing a phone, so parallel cash checkouts cannot both pass the open-cash-order limit
A transaction-scoped advisory lock on the customer, taken before the order is inserted, serialises one customer's cart and offer checkouts on the `manual` provider, so two placements racing at `manual_max_open_orders` place one (ADR-049 d14)

Failure behaviour:

Order creation, line creation, payment creation, consent recording, idempotency recording, and cart clearing occur in one transaction
If any step fails, the entire operation rolls back
No payment redirect is returned unless the order transaction commits

Traceability: F-042, F-044, F-046, F-052, F-053.

FR-07: Process and independently verify payment

As a customer,
I can complete an online payment through the payment provider,
so that my order can be fulfilled securely.

Given:

A valid pending order and live payment attempt exist

When:

The customer is redirected to the payment provider chosen at checkout, or, on the `manual` provider, the administrator contacts the customer to arrange payment
The provider sends a callback to its own route
The system reconciles a payment
An administrator performs permitted manual confirmation: it applies a live attempt of an uncancelled order, and records a late capture for any other (on `manual` the reference is optional, unique per provider when given)

Then:

The callback event is stored
Signature verification occurs where supported
The server independently queries the payment provider named on the payment row, never the one named in the URL
The confirmed currency and amount must equal the order total
The payment becomes paid only after independent verification
STL lines enter awaiting_delivery atomically
Physical lines become eligible for production
Relevant offers are closed
Order status is recomputed
Audit, history, notification, and outbox records are created

Negative cases:

A callback alone is never proof of payment
Invalid signatures are rejected and alerted
Only configured online providers are routable; cash never, and the mock provider never in production
An event whose provider differs from its payment's provider is stored and ignored
Underpayment is not accepted
Duplicate provider events do not apply a payment twice
A second live payment for the same order is prohibited
Unauthorized users cannot manually confirm payment
A reference already on another payment of the same provider is refused, also for two confirms racing on one reference
The `manual` provider takes no webhooks and is never reconciled
A manual confirmation of a payment that already holds money never changes its reference: another reference is refused as a likely second transfer

State transitions touched:

Pending → processing
Pending or processing → paid
Pending or processing → failed
Pending or processing → expired
Failed or expired attempt, cancelled order, or a captured amount that does not match the total, then a confirmed capture → late capture: `late_captured_at` recorded, status unchanged (a mismatched live attempt becomes failed), automatic late-capture refund obligation, alert, order and lines untouched
A duplicate success for an attempt already paid → no change

Concurrent access:

Duplicate callbacks are deduplicated by provider event identifier
At most one live payment exists per order
Simultaneous callback and reconciliation processing must result in one payment application
Applying a result locks the order row, then its lines, then the payment (ADR-024 lock order)
STL ownership uniqueness prevents paying twice for the same STL

Failure behaviour:

The callback endpoint persists the event and responds quickly
External provider queries occur without holding database locks
A failed provider query leaves payment unresolved rather than paid
A late provider success is never applied to the order; the captured money becomes a refund obligation
The hold release never cancels an order whose provider check failed or timed out, or that has an unprocessed webhook event; it skips and alerts. A `manual` order is released at the end of `manual_payment_hold_period`, and money confirmed after that is a late capture with its refund obligation
A payment retry locks the order and re-checks it, so it cannot add a payment to an order the hold release has cancelled
Stuck payments are retried through reconciliation
If provider queries are unavailable, payment requires administrator confirmation against the provider dashboard

The SRS identifies reconciliation as critical because a lost callback could otherwise leave a customer charged without receiving the purchased product.

Cash orders never enter this flow: they have no payment attempt, and their cash is recorded at handover (FR-20).

Traceability: F-047 through F-051.

FR-08: Fulfill physical order lines

As an administrator,
I can move physical order lines through production and fulfillment,
so that customers receive accurate status information.

Given:

An online order's payment has been independently confirmed, or the order is a cash order
The order contains one or more physical lines

When:

The administrator opens the fulfillment queue, which never lists unpaid online orders
The administrator marks start printing
Marks an item ready, shipped, delivered, ready for pickup, picked up, or returned

Then:

Every line follows the valid state machine
Order-level status is recomputed from payment and line statuses
The customer is emailed and notified at ready ("your order is finished"), shipped, ready for pickup, and delivered or picked up
Start printing is internal: no email or notification, and the customer sees the line as received
Every transition records actor, timestamp, prior state, new state, and notes

Negative cases:

Invalid or skipped state transitions are rejected
Customers cannot directly set fulfillment states
A delivery line cannot use pickup-only transitions
A pickup line cannot use shipping-only transitions
A returned item is not automatically treated as terminal
On a cash order, delivered and picked up are reached only through the cash handover (FR-20)
Any physical transition on an unpaid online order is rejected with an invalid-state conflict; an online payment that reached paid (paid, partially refunded or refunded) allows them, and the hold release's cancellation of pending lines is the only exception
Customers never see start printing: the line shows as received and the history omits it

State transitions touched:

Delivery:

pending → in_production → ready_to_ship → shipped → delivered

Pickup:

pending → in_production → ready_for_pickup → picked_up

Return resolution:

returned → shipped | in_production | refunded (paid line) | cancelled (unpaid cash line, no refund)

Pickup no-show:

ready_for_pickup → cancelled (administrator, with reason refused, no_show or other)

$0 unpaid cash line:

shipped → cancelled (administrator, reason other)

Concurrent access:

Every transition locks the order row first, then the line (ADR-024 lock order)
A customer cancellation racing start printing serialises on the order row, whichever line each touches
Exactly one operation succeeds according to the committed state
Concurrent administrator transitions from the same original state must not both succeed

Failure behaviour:

Status, history, order projection, audit record, notification, and outbox changes commit atomically
An email failure does not roll back the fulfillment transition
Invalid transitions leave all states unchanged

The required payment, order, digital-line, physical-line, and offer state machines are defined explicitly by the SRS.

Traceability: F-060 through F-068.

FR-09: Cancel an eligible order line

As a verified customer,
I can cancel an eligible physical order before printing begins,
so that I am not charged for work that has not started.

Given:

The customer owns the order
The order has at least one live (not cancelled) physical line, and is a cash order or has an online payment that reached paid
Every live physical line is still pending: the administrator has not marked start printing; lines already cancelled are ignored

When:

The customer requests cancellation

Then:

The line becomes cancelled
A refund obligation is created when money must be returned; an unpaid cash order creates none
The order's can_cancel flag reflects whether this request can succeed
Order status is recomputed
Audit and notification records are created

Negative cases:

STL lines cannot be self-cancelled
A physical line already in production cannot be self-cancelled
Another customer cannot cancel the order
Terminal lines cannot be cancelled again

State transitions touched:

Physical pending → cancelled
Paid order → cancelled, partially refunded or refunded, depending on remaining lines and earlier refunds
Unpaid cash order → cancelled

Administrator cancellations from ready_to_ship, returned or ready_for_pickup record a reason: refused, no_show (ready_for_pickup only) or other; see FR-20 for the cash block.

Concurrent access:

Cancellation locks the order row, then every physical line in id order, before checking them; start printing locks the same order row first
Only one transition may commit
The losing request receives an invalid-state conflict

Failure behaviour:

Cancellation and refund-obligation creation occur atomically
The cancellation refund is the line's remaining balance, and none is created when that is zero
A failed cancellation refund stays owed in the obligations queue until reissued; the cancellation record is never lost

Traceability: F-033, F-066.

FR-10: Issue and track refunds

As an administrator,
I can issue full or partial refunds by order line,
so that customer obligations are recorded and settled correctly.

Given:

The order has a confirmed payment
The refunded lines are paid lines: a cancelled line of a cash order was never paid and has nothing refundable
The administrator records the refund, pays it by hand (provider dashboard or cash), then settles it; the platform never calls a provider refund API
The refundable amount is greater than zero
The requested amount does not exceed the remaining refundable balance

When:

The administrator refunds one or more lines (there is no shipping fee to refund)
A payment reversal or chargeback is confirmed, and is recorded as a chargeback (its own record, ADR-042), outside the obligations queue: it absorbs the payment's open refunds and splits the rest of the charge per line

Then:

A refund record and refund-line records are created
A refund of part of a line leaves the line in its state; a line becomes refunded only when its refunds cover its whole total
A refund that would empty an unfinished physical line is rejected; the line is cancelled instead
The obligation remains pending until confirmed settled
Relevant line and order statuses are recomputed
Refunded STL lines become refunded; one not yet sent leaves the delivery queue
A cash payment is refunded up to the cash recorded
When refunds cover all paid money, the order becomes refunded
Audit and customer-notification records are created

Negative cases:

The total refunded amount cannot exceed the paid amount, and no line's refund can exceed its line total minus its items in pending, settled and owed refunds and in chargebacks (an owed refund's amount stays reserved for its reissue)
A settled refund cannot be voided; a voided one cannot be reissued; a refund whose line is already refunded or cancelled cannot be voided
A refund item on a cancelled cash line is rejected
The same amount cannot be refunded twice
Unpaid orders cannot be refunded, including cash orders whose cash has not been recorded
Unauthorized users cannot issue refunds
Refunding an STL line never deletes its delivery record

State transitions touched:

Paid → partially_refunded
Paid or partially_refunded → refunded
Digital awaiting_delivery or delivered → refunded
Physical terminal state → refunded (only when fully refunded)
Refund pending → settled, failed or voided; failed (not reissued) → voided
Payment refunded → partially_refunded → paid when a refund fails or is voided
Refund pending → failed → stays owed in the obligations queue, changes no line state, never counts toward refunded status, and is reissued as a new pending refund

Concurrent access:

Refund requests use idempotency protection
Concurrent partial refunds lock the order row, then its lines, then its payments, then the refund, and recheck the remaining balance; a chargeback takes the payment's open refunds next and inserts last (ADR-042 d8)
Only amounts within the remaining balance may commit

Failure behaviour:

Every refund is manual in V1: the obligation remains in the administrator queue until the administrator settles it after paying it
A failed refund must not remove or falsely settle the obligation; it stays owed until reissued
STL line refund and confirmed refund state changes occur transactionally

Traceability: F-070 through F-074.

FR-11: Upload and version STL assets

Removed by ADR-019. STL files are never uploaded to the platform; they stay on the administrator's own drive. F-080 to F-082 are removed.

FR-12: Deliver purchased STL files manually

As an administrator,
I can see every paid STL line still owed to a customer and record when I have emailed it,
so that no customer is forgotten and every customer knows their file was sent.

Given:

The administrator is authenticated and authorized
An STL line's payment has been independently verified

When:

The administrator opens the STL delivery queue
Emails the file from their own drive to the address shown
Marks the line delivered

Then:

The queue lists every STL line in awaiting_delivery, oldest first, with order number, product, customer and the email recorded at checkout
Marking delivered records when and by which administrator
The order status is recomputed
The customer receives an in-app notification and an email saying the file was sent
The action is audit-logged

Negative cases:

A line whose payment is not verified never appears in the queue and cannot be marked delivered
A line already delivered or refunded cannot be marked delivered again
A refunded line awaiting delivery leaves the queue and must not be sent
Non-administrators cannot see the queue or mark lines delivered; customers get the admin boundary's 404
A customer cannot buy an STL they already own (a paid, unrefunded line)

State transitions touched:

Digital line pending → awaiting_delivery after payment verification
Awaiting_delivery → delivered by the administrator
Awaiting_delivery or delivered → refunded

Concurrent access:

Marking delivered and refunding the same line both lock the order row, then that line; exactly one succeeds
Two administrators marking the same line delivered produce one delivery record and one notification
Two parallel checkouts for the same STL by one customer: the ownership constraint lets only one hold a live line

Failure behaviour:

The delivery record, order projection, audit row and notification outbox commit atomically
An email-provider failure for the "file sent" notification never rolls back the delivery record

Traceability: F-083, F-089 (ADR-019; F-084 to F-088 removed).

FR-13: Negotiate an STL offer

As a verified customer,
I can submit and negotiate an offer for an STL product,
so that I may purchase it at an agreed price.

Given:

The product is an active STL product
The customer does not already own it
No live offer exists for that customer and product
The offered amount meets the configured minimum
No rejection cooldown is active

When:

The customer submits, counters, accepts, or withdraws an offer
The administrator accepts, rejects, or counters

Then:

Every round is appended to permanent negotiation history
The turn changes to the other party after a counter
The response deadline resets
Acceptance freezes the price
A customer-specific one-time checkout is created
Acquisition through another route automatically closes the offer

Negative cases:

Offers cannot be submitted for physical products
Offers below the configured floor are rejected
Only the party whose turn it is may respond
A second live offer for the same customer and product is prohibited
An expired checkout cannot be paid
A rejected offer cannot be reopened during cooldown

State transitions touched:

No offer → awaiting_admin
Awaiting_admin ↔ awaiting_customer
Awaiting state → accepted, rejected, expired, or withdrawn
Accepted → paid, checkout_expired, or auto_closed

Concurrent access:

A unique database constraint permits one live offer per customer and product
Concurrent acquisition and offer acceptance must lock or recheck ownership
Only one path may charge the customer for the same STL

Failure behaviour:

Failed counter or acceptance leaves the prior turn unchanged
Expiration jobs close overdue offers
A failed checkout does not alter the frozen agreed price until the checkout window expires

Traceability: F-090 through F-098.

FR-14: Manage reviews and wishlist

As a verified customer,
I can review products and maintain a wishlist,
so that I can share feedback and save products.

Given:

The customer is authenticated and verified
The product is visible

When:

The customer creates or edits a review
Adds or removes a wishlist item

Then:

One active review is stored per customer and product
Ratings are integers from one through five
A verified-purchase badge reflects current purchase evidence
Product rating aggregates are updated
Wishlist totals become available to administrators

Negative cases:

Duplicate active reviews are prohibited
Links, prohibited content, or excessive submissions may be rejected
Hidden reviews do not contribute to public aggregates
Unverified users cannot review or modify a wishlist
Customers cannot edit other customers’ reviews
An unpaid or refused cash purchase never earns the badge, even when the rest of its order was paid

State transitions touched:

No review → visible review
Visible review → edited or hidden
Hidden review → restored
Wishlist absent ↔ present
Unverified badge ↔ verified-purchase badge

Concurrent access:

A unique constraint prevents duplicate reviews or wishlist items
Rating aggregates must remain correct during concurrent review updates
A purchase being paid (online verification or cash handover) or refunded triggers badge recomputation

Failure behaviour:

Review and aggregate updates occur in one transaction
Failed moderation leaves the previous visibility and aggregate state unchanged

Traceability: F-100 through F-104.

FR-15: Submit and process Bring Your Idea requests

As a visitor,
I can submit a custom-printing request with reference images,
so that Bekaa3D can evaluate and quote my idea.

Given:

Captcha validation succeeds
Rate limits are not exceeded
Attachments meet size, count, and content requirements

When:

The visitor submits the form
An administrator processes the lead

Then:

The request enters the administrator pipeline
Images are validated, re-encoded, malware-scanned, and stored privately
The administrator can record contact, quotation, progress, outcome, and notes
Funnel analytics can distinguish won and lost requests

Negative cases:

Invalid captcha is rejected
Unsupported or malicious files are rejected
Excessive submissions are rate-limited
Attachments are never publicly accessible
The workflow cannot accept online payment in V1

State transitions touched:

new → contacted → quoted → in_progress → completed → closed

Lost exits are allowed from contacted or quoted.

Concurrent access:

Conflicting administrator transitions from the same state must not both commit
Duplicate submissions may be detected or rate-limited but are not automatically merged without a confirmed business rule

Failure behaviour:

A request is not created unless its accepted attachment metadata is consistent
Orphaned uploads are removed
Expired attachments are deleted by a scheduled job
Notification failure does not remove the submitted request

Traceability: F-106, F-107.

FR-16: Submit and manage contact messages

As a visitor,
I can submit a contact message,
so that I can communicate with the business without registration.

Given:

Captcha succeeds
Rate limits are not exceeded

When:

The visitor submits the contact form
An administrator reads or archives the message

Then:

The message enters the administrator queue
Its status can move through new, read, replied, and archived
The action is audit-logged where appropriate

Negative cases:

Spam or rate-limited submissions are rejected
Invalid contact details are rejected
Visitors cannot read administrator queues

State transitions touched:

new → read → replied → archived

Concurrent access:

Concurrent administrator changes must validate the current state
Repeated form submissions are separate messages unless an explicit duplicate policy is added

Failure behaviour:

A failed notification does not remove the stored contact message
Invalid attachments or fields prevent the submission from committing

Traceability: F-108.

FR-17: Deliver transactional notifications

As a customer,
I can receive localized email and in-app notifications,
so that I know when important account, payment, offer, order, refund, and STL-sent events occur.

Given:

A business event requiring notification commits

When:

The transaction completes
The outbox worker processes pending messages

Then:

An outbox record is written in the same transaction as the business event
Email is rendered from the transactional template
Delivery is retried with exponential backoff
In-app notifications support read and unread state

Negative cases:

Email-provider failure must not roll back payment, order, or fulfillment changes
Sensitive data must not be exposed in notification payloads
Duplicate processing must not send uncontrolled duplicate messages
Start printing never produces a customer email or notification

State transitions touched:

Outbox pending → sending → sent or failed
Notification unread → read

Concurrent access:

Multiple workers must not deliver the same outbox item simultaneously
Worker claiming must use locking or an atomic status update

Failure behaviour:

Failed messages remain retryable
Repeated failures trigger an operational alert
The administrator can observe outbox backlog through monitoring

Traceability: F-032, F-105, F-130.

FR-18: Operate the platform through the administrator dashboard

As an administrator,
I can manage business queues, settings, users, and analytics,
so that I can operate Bekaa3D without direct database access.

Given:

The administrator is authenticated
MFA is completed where enabled

When:

The administrator opens an operational queue
Changes a typed setting
Reviews analytics
Inspects audit history

Then:

Orders (including cash orders awaiting handover), offers, refunds, payments, reviews, custom requests, and messages can be filtered and processed
Cash limits (switch, open cash orders per customer or phone, maximum cash total) are typed settings, and cash payment blocks can be listed and cleared
Typed settings are validated before saving
Every setting change records previous value, new value, actor, and timestamp
Revenue is attributed by order line and product stream
Analytics include purchases, customers, offers, wishlist, ratings, best-selling STLs, and Bring Your Idea conversion

Negative cases:

Non-administrators receive no confirmation that protected resources exist
Invalid setting types or ranges are rejected
Order status cannot be assigned directly
Audit entries cannot be edited through normal administration

State transitions touched:

Settings old value → new value
Operational records follow their individual state machines
Administrator audit event appended

Concurrent access:

Checkout must recheck the accepting-orders setting inside its transaction
Two administrators editing the same protected setting must produce deterministic conflict or last-commit behavior with both attempts audited
Queue actions must revalidate current record state before committing

Failure behaviour:

A dashboard write and its audit entry commit atomically
Analytics failure must not affect operational transactions
Unavailable analytics should return an error rather than fabricated zero values

Traceability: F-114 through F-128.

FR-19: Execute reliability-critical scheduled jobs

As the system,
I can execute scheduled maintenance and recovery jobs,
so that temporary failures do not permanently block customers or lose business obligations.

Given:

The worker and scheduler services are healthy

When:

A scheduled cadence is reached

Then:

Email outbox runs every minute
Offers and stale online checkouts expire every five minutes (a stale checkout is released only when the provider confirms it unpaid)
Stuck payments are reconciled every fifteen minutes
Unverified accounts, expired attachments, and orphan files are processed daily
Backup integrity is verified daily
Database partitions, retention rollups, and IP-hash salt rotation run monthly

Negative cases:

Two scheduler instances must not process the same logical job concurrently
Failed reconciliation must not mark a payment paid
Backup checks must not report success without verifying backup integrity
Partition maintenance must not delete data still inside its retention period

State transitions touched:

Outbox pending → sent or retrying
Offer active → expired
Unpaid online order → cancelled (a cash order is never expired by a job)
Payment unresolved → paid, failed, expired, or manual review
Attachment active → purged
Detail partition active → aggregated and pruned

Concurrent access:

Jobs must use distributed locking, unique job execution, or idempotent processing
Job processing racing user activity must recheck the current state before changing it

Failure behaviour:

Failed jobs remain observable and retryable
Cron-liveness monitoring alerts when expected execution stops
Payment reconciliation, partition creation, backup verification, disk pressure, and outbox backlog require operational alerts

The required jobs and their cadences are defined by the SRS.

FR-20: Record cash on delivery or at pickup

As an administrator,
I can record the cash collected for a cash order in the same action that marks it delivered or picked up,
so that the payment is confirmed by a documented manual check and the order completes.

Given:

The order's payment method is cash and no cash has been recorded
The order has at least one live (non-cancelled) line, and every live line is shipped (delivery) or ready for pickup (pickup)
The courier has reported the order delivered and paid, or the customer paid at the counter

When:

The administrator records the cash handover with the amount collected

Then:

The amount equals the sum of live line totals and is above zero; it is the full amount the customer paid, even if the courier later remits less
Every live line becomes delivered or picked up
One payment is created with provider cash, status paid, the amount, and the recording administrator
Order status and the Verified Purchase badge are recomputed
History, audit, notification, and the delivered or picked-up email with the cash receipt are written

Negative cases:

A different amount is rejected and nothing changes
A line not yet shipped or ready for pickup rejects the handover
An order with no live line rejects the handover
A second cash payment on the same order is refused by a unique index
An online order cannot use the cash handover
The transition endpoint cannot mark a cash order's line delivered or picked up
Customers cannot record cash
No callback, webhook, or job can create a cash payment

State transitions touched:

Physical shipped → delivered, or ready_for_pickup → picked_up, for every live line
No payment → paid (cash)
Order in progress → completed

Refusal:

shipped → returned → cancelled, ready_to_ship → cancelled, or ready_for_pickup → cancelled, each with reason refused, no_show (ready_for_pickup only) or other, and no refund obligation
When a cancel leaves the order with no live line, and every line cancelled from those states carries refused or no_show (at least one), a cash payment block is inserted for the customer and the order's phone hash, in the same transaction and under the phone advisory lock; the outcome does not depend on cancel order
Refusing only some lines, or any other cancel, never blocks
If a refusal leaves only lines totalling zero, the administrator cancels them (other) instead of a handover
An administrator lists and clears blocks

Concurrent access:

The handover locks the order row, then every line in id order (ADR-024 lock order), so it cannot deadlock against a line transition or cancellation
Two administrators recording the same handover: one succeeds, one gets a conflict; one payment, one audit row, one email
A handover racing an administrator cancellation on the same order has exactly one winner

Failure behaviour:

Line changes, payment creation, projection, history, audit, and outbox commit atomically
An email failure does not roll back the handover

Traceability: F-053, F-054, F-065.

FR-21: Confirm receipt or report a problem

As a verified customer,
I can confirm that I received my order or report a problem with it,
so that the administrator knows the outcome of the delivery.

Given:

The customer owns the order
At least one line is delivered or picked up

When:

The customer presses "I got it" or "Report a problem" on the order page

Then:

"I got it" records receipt confirmation on the delivered or picked-up lines
"Report a problem" records the report and creates a contact message linked to the order
Neither changes a line's state, and the order completes without them

Negative cases:

Another customer's order is not found
An order with no delivered or picked-up line rejects both actions
Following a link in the email never changes state; the action is a signed-in request from the order page

State transitions touched:

None; timestamps only

Concurrent access:

Confirming twice keeps the first confirmation

Failure behaviour:

The report and its contact message commit together

Traceability: F-069.
