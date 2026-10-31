# The notification contract

How in-app notifications are typed, shaped, owned and read. Introduced by
VS-008; the endpoints are `GET /api/v1/me/notifications` and
`PATCH /api/v1/me/notifications/{notification_id}`.

VS-008 builds the **channel**. It deliberately ships no production event
semantics — the slices that own orders, payments, offers, refunds and STL delivery
define those when they are built. Since ADR-019, `download` is the category for
the "STL file sent" event (`payload.event = "stl.delivered"`, VS-023b).

## Type: a stable high-level category

`notification_type` is a PostgreSQL enum with seven values: the six from
`database-design.md` §12.3, plus `custom_request`, which VS-034 added (ADR-030):

```
account   order   payment   refund   offer   download   custom_request
```

The design is explicit that this enum stays a *category*: "The specific event is
carried in the JSON payload; the enum remains a stable high-level category."

That split is load-bearing. A new business event needs a new `payload.event`
value and no migration; a new *category* is a schema change, because adding a
value to a PostgreSQL enum is DDL. The friction is intentional and sits in the
right place.

## Payload

The payload is **supporting presentation data, not the source of truth** for
orders or payments. Never read it to decide anything; read the owning context's
tables through their service interfaces.

Rules enforced by `app.engagement.domain.payload`:

| Rule | Detail |
| --- | --- |
| Must be a JSON object | Not an array, string or number. Keys must be strings. |
| Must contain `event` | A non-empty string. |
| `event` values are open in V1 | No enum, no registry. Producer slices define them. |
| Maximum 16 KiB | Measured after deterministic compact UTF-8 serialisation. |
| No secrets or sensitive data | FR-17: "Sensitive data must not be exposed in notification payloads." |

### Events in use

| `payload.event` | Type | Recipient | Other keys | Slice |
| --- | --- | --- | --- | --- |
| `custom_request.submitted` | `custom_request` | every active administrator | `custom_request_id`, `project_title`, `title` | VS-034 |
| `order.problem_reported` | `order` | every active administrator, in the report's transaction (a failure fails the report, ADR-041) | `order_id`, `order_number`, `contact_message_id`, `title`; never the message, email or phone | VS-029b |
| `payment.confirmed` | `payment` | the customer | `order_id`, `order_number` | VS-023 |
| `order.placed` | `order` | the customer, for a cash order | `order_id`, `order_number` | VS-028 |
| `order.awaiting_payment` | `order` | the customer, for an order on the `manual` provider: the administrator will make contact to arrange payment (ADR-049) | `order_id`, `order_number`, `total_cents`, `currency`; never the phone | VS-050 |
| `payment.alert.manual_payment_due` | `payment` | every active, verified administrator, once per `manual` attempt ([`payment-recovery.md`](payment-recovery.md)) | `kind`, `payment_id`, `order_id`, `order_number`, `provider` | VS-050 |
| `offer.submitted` | `offer` | every active administrator | `offer_id`, `product_id`, `product_name`, `amount_cents`, `currency` | VS-039 |
| `offer.expired` | `offer` | the customer | `offer_id`, `product_id` | VS-039 |
| `offer.countered` | `offer` | the customer (admin counter) or every active administrator (customer counter) | `offer_id`, `product_id`, `product_name`, `amount_cents`, `currency`, `responds_by` | VS-040 |
| `offer.accepted` | `offer` | the customer, and every active administrator when the customer accepted | `offer_id`, `product_id`, `product_name`, `agreed_amount_cents`, `currency`, `checkout_expires_at` | VS-040 |
| `offer.rejected` | `offer` | the customer | `offer_id`, `product_id`, `product_name`, `cooldown_until` | VS-040 |
| `offer.withdrawn` | `offer` | every active administrator | `offer_id`, `product_id`, `product_name` | VS-040 |
| `offer.expiring_soon` | `offer` | the customer | `offer_id`, `product_id`, `product_name`, `amount_cents`, `currency`, `responds_by` | VS-040 |
| `offer.checkout_expired` | `offer` | the customer | `offer_id`, `product_id` | VS-040 |
| `stl.delivered` | `download` | the customer | `order_id`, `order_number`, `item_id`, `product_name` | VS-023b |
| `order.cancelled` | `order` | the customer, once per cancel request ([`cancellation.md`](cancellation.md)) | `order_id`, `order_number`, `items` (`item_id`, `product_name`), `order_cancelled`, `amount_due_cents`, `refund_cents`, `currency` | VS-031 |
| `order.ready_to_ship`, `order.shipped`, `order.ready_for_pickup`, `order.delivered`, `order.picked_up` | `order` | the customer, once per order per step ([`fulfillment.md`](fulfillment.md)) | `order_id`, `order_number`, `step`, `fulfillment_method`, `payment_method`, `delivery_fee_note`, `receipt_actions`; `pickup_address`, `pickup_hours` for pickup; `cash_receipt` after a cash handover | VS-029 |

Emails with them (outbox templates; no phone, hash or address ever appears in a payload):
- `order_payment_confirmed` (VS-023): `order_id`, `order_number`, `total_cents`, `currency`; VS-028 adds `fulfillment_method`, `estimated_dispatch_at` and `delivery_fee_note` (delivery only).
- `order_cancelled` (VS-031): the `order.cancelled` payload above; a paid cancel also sends VS-030's `order_refund_issued`.
- `order_cash_placed` (VS-028): `order_id`, `order_number`, `amount_due_cents`, `currency`, `fulfillment_method`, `estimated_dispatch_at`, `delivery_fee_note` (delivery only), `pickup`.
- `order_awaiting_payment` (VS-050): `order_id`, `order_number`, `total_cents`, `currency`: the order is placed and the administrator will contact the customer to arrange payment.

### On `event`

`payload["event"]` is the discriminator the database design refers to. VS-008
requires the key to *exist* and forbids nothing about its value.

Requiring it now rather than later is deliberate: it stops the first two
producing slices inventing two different conventions, and adding a required
field to an already-populated table means a backfill. Tests use neutral values
such as `account.test`.

### On the 16 KiB ceiling

**A V1 technical safety limit, not an SRS-defined business value.** Nothing in
the specification names a payload size. It exists so that a defect in a future
producing slice cannot write a multi-megabyte JSONB row that then has to be read
back on every page of the notification list. Revisit it if a real payload ever
approaches it — no current one comes close.

Size is measured on a compact, key-sorted, UTF-8 serialisation, so two payloads
differing only in key order cannot land on opposite sides of the limit.

### On sensitive data

A payload is rendered in a browser and is readable by anyone who can dump the
table. An amount and an order reference are fine. A card reference, a token, a
password-reset link or a full address are not — those belong in the owning
context's table, behind that context's authorization.

## Read state

Persisted as a single nullable column, `read_at`:

```
read_at IS NULL      unread
read_at IS NOT NULL  read, at that moment
```

The API exposes a boolean `read`, and **not** `read_at`. `read` is derived on
every render from `read_at is not None`, so the two can never drift — which a
stored boolean sitting beside a timestamp eventually would.

`read_at` keeps its **first-read** meaning. Marking an already-read notification
read again is a no-op on the timestamp (`COALESCE(read_at, now())`), so it
records when the customer first saw the notification, not when they last tapped
it. Marking unread sets it back to `NULL`; both directions are supported and
both are idempotent.

There is no `updated_at` column. `read_at` is the only mutable field, so a
second mutation timestamp would carry no information the first does not.

### Concurrency

Marking read is **idempotent state assignment**, not a read-modify-write. It
computes nothing from the previous value, writes no audit chain, and maintains
no invariant spanning rows — so it uses a single atomic `UPDATE` and
deliberately **no** `SELECT ... FOR UPDATE`.

This is a real difference from VS-007's settings editor, which needs the row
lock because its audit trail must record a truthful `before → after` chain. Here
every interleaving of two concurrent calls leaves a legitimate state, and the
contract for simultaneous `read=true` / `read=false` is simply **last database
writer wins**. HTTP execution order is not guaranteed, so the final state is not
claimed to correspond to whichever click happened first in wall-clock time.

## Ownership

A user may view or mark only their own notifications.

Ownership is encoded in the SQL predicate — `WHERE id = ... AND user_id = ...` —
never by loading a row and comparing in Python. A filter that is part of the
query cannot be forgotten on one branch the way a later `if` can.

Zero rows returned means **`404 NOT_FOUND`**, identically for "no such
notification" and "someone else's notification". A `403` on the second case
would confirm the row exists and let a customer enumerate other people's
notification ids.

| Endpoint | Level | Notes |
| --- | --- | --- |
| `GET /me/notifications` | Authenticated | Verification not required — reading is not a write. |
| `PATCH /me/notifications/{id}` | Verified Customer; owner | Plus CSRF, per SEC-03. |

An unverified account gets `403 EMAIL_VERIFICATION_REQUIRED` on the PATCH. The
`current_verified_user` dependency reads the user row rather than trusting the
access token's `ver` claim, so a customer who has just verified is not refused
for the remainder of that token's fifteen minutes.

## Creating notifications

`app.engagement.public.create_notification` is the **only** sanctioned write
path (VS-012c moved it there from `application.services.notification_writer`,
which now holds the logic as `write_notification`). It takes the caller's `AsyncSession` and
does not commit, so a notification lands in the same transaction as the business
event that caused it:

```
business mutation
create_notification(...)
email outbox insert, if the event also warrants email
COMMIT
```

If the payment rolls back, the notification announcing it rolls back with it.

Other bounded contexts must not import `NotificationModel`,
`NotificationRepository`, or write raw SQL against `notifications`.
`tests/unit/engagement/test_notification_boundary.py` enforces this.

There is no message broker, no event bus and no background notification worker.

## Notification vs EmailOutbox

Two different things that the glossary is careful to keep apart — a Notification
is "not an Email Outbox record", and an Email Outbox record is "not a
Notification".

| | Notification | EmailOutbox |
| --- | --- | --- |
| What it is | A durable, user-owned in-app record | A queue of email to an external provider |
| Lifecycle | `unread → read` | `pending → sending → sent / failed` |
| Machinery | None | Retry, backoff, attempt count, worker claiming |
| Context | Engagement | Platform |

Notification creation is **not** routed through the email outbox, and neither is
derived from the other. A business event that warrants both simply calls both
services inside the same transaction. Chaining them would let an email-provider
failure affect in-app state, which is precisely the coupling ADR-011 exists to
prevent.

To be accurate about what this does and does not guarantee: a notification
insert **can** fail, and it rolls its transaction back when it does. What it has
no separate lifecycle for is *external delivery* — once the transaction commits,
the notification is already where the customer will read it, because the
customer reads this table directly. Email leaves the system and therefore needs a
delivery lifecycle; an in-app notification does not.

## Links in emails

Every link an email carries points at the **frontend**, never at the API, and a
single-use token travels in the URL **fragment**:

| Email | Link |
| --- | --- |
| Verification (and resend) | `{FRONTEND_BASE_URL}/verify-email#token=<token>` |
| Password reset | `{FRONTEND_BASE_URL}/reset-password#token=<token>` |

- `FRONTEND_BASE_URL` is its own setting (`.env.example`), separate from the
  API's `BASE_URL`.
- The fragment (`#...`) is never sent to any server by a browser, so the token
  never reaches an access log, a proxy or a `Referer` header. The frontend
  reads it with JavaScript and submits it in a `POST` body to
  `/api/v1/auth/verify-email` or `/api/v1/auth/password-reset/confirm`.
- Those API endpoints stay POST-only. A link used to point straight at them with
  `?token=`, so following it from an inbox answered `405` and put the token in
  the query string (BUG-09).

## Retention

**Intentionally undecided.** `database-design.md` records the retention policy
for notifications as "not numerically specified", and
`entities-and-business-rules.md` asks for "soft deletion or retention-based
pruning **after a formal retention decision**."

No such decision exists, so VS-008 adds no pruning job, no `deleted_at` column
and no retention constant. Inventing a number here would be an unapproved
operational decision dressed up as an implementation detail.

The foreign key is `ON DELETE CASCADE`. Never-verified accounts are legitimately
physically purged (FR-02), `notifications.user_id` is `NOT NULL` so `SET NULL`
is not representable, and verified-customer deletion remains anonymisation
rather than deletion.
