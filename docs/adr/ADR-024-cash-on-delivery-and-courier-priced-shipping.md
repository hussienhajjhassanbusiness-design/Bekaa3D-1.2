# ADR-024: The courier prices and collects shipping; physical-only orders may be paid in cash on delivery

**Status:** Accepted
**Date:** 2026-10-10
**Source basis:** Business decision by the owner, 2026-10-08; SRS §1, §3, §5, §7, §8, §9, §15, §16, §19, §20, §22, §23, §27, §29, §30
**Supersedes:** nothing in full. Reopens the provider choice in [ADR-012](ADR-012-payment-provider-abstraction.md) ("Whish is V1's provider"); ADR-012's abstraction decision stands.

## Context

The SRS (v1.1) had the platform charge shipping: admin-managed flat-rate zones, a shipping line in every delivery order total, an optional free-shipping threshold, and shipping refunds. Every order had to be paid online through Whish before anything was made, and cash on delivery was out of scope.

The business works differently. The courier sets the delivery fee and collects it from the customer at the door. Many Lebanese customers prefer to pay cash when the goods arrive, and the owner wants to offer that for physical goods. The online provider is also no longer fixed: Whish, a card gateway, or both are being considered.

An emailed STL file cannot be taken back, so STL purchases must still be paid and verified online first.

## Decision

1. **The platform never charges shipping.** No shipping line in the order total, no shipping zones, no free-shipping threshold, no shipping refunds. Checkout and emails say "delivery fee paid to the courier on delivery". `total = subtotal + tax` (tax is 0 in V1).
2. **Payment method is chosen at checkout: `online` or `cash`.** It is snapshotted on the order (`orders.payment_method`) and never changes. Cash is allowed only when every line is physical; an order with any STL line is paid online. Pickup orders follow the same rule ("cash at pickup").
3. **A cash order is placed unpaid and has no `payments` row while unpaid.** It has no checkout hold, so stale-checkout release, reconciliation and payment retry never touch it. Its physical lines are eligible for production as soon as it is placed.
4. **Cash is recorded once per order, at handover.** One admin action, "record delivery and cash", requires every live line to be `shipped` (delivery) or `ready_for_pickup` (pickup). In one transaction it marks them `delivered` / `picked_up` and creates one `payments` row (`provider = 'cash'`, `status = 'paid'`, amount = sum of live line totals, recorded by the admin). The cash entered must equal that amount exactly. This is the documented manual admin confirmation, so a callback is still never proof: no external input can create a cash payment.
5. **Refusal costs nothing but the work.** A refused or unreachable delivery goes `shipped → returned → cancelled`; a pickup no-show goes `ready_for_pickup → cancelled`. An unpaid cash line creates no refund obligation. Either path sets `users.cash_payment_blocked_at`, which removes cash from that customer's checkout until an administrator clears it.
6. **COD abuse limits** are admin-editable settings: `cash_payment_enabled` (default `true`), `cash_max_open_orders` (default 1 unpaid, uncancelled cash order per customer, checked under the cart lock), `cash_max_order_total` (default 10 000 cents, USD). Every physical order snapshots a contact phone (the address's phone for delivery, a phone entered at checkout for pickup) so the administrator can call before printing.
7. **Physical line states.** Delivery: `pending → in_production → ready_to_ship → shipped → delivered`. Pickup: `pending → in_production → ready_for_pickup → picked_up`. `in_production` ("start printing") is internal: no email or notification, and customers see it as "Received". Customers are emailed and notified at `ready_to_ship` ("your order is finished"), `shipped`, `ready_for_pickup` and `delivered` / `picked_up`. Self-cancel is allowed only while every physical line is `pending`.
8. **Receipt confirmation is optional.** The delivered / picked-up email links to the order page, where a signed-in customer can press "I got it" (sets `receipt_confirmed_at`) or "Report a problem" (creates a contact message linked to the order and sets `problem_reported_at`). The order completes without either.
9. **Online refunds and cash refunds.** A cash order can be refunded only after its cash is recorded, always with method `manual`, up to the cash recorded.
10. **The online provider is an open decision** (SRS §30), due before VS-032. The provider port and mock adapter stay; the webhook route becomes provider-neutral (`/api/v1/webhooks/payments/{provider}`).
11. **The address book stays** (recipient, Lebanese phone, address); the phone is the courier's contact.

## Consequences

+ No zone table, zone admin, threshold or shipping-refund arithmetic: VS-027 leaves the plan, and the mixed-order partial-refund path loses its shipping component.
+ Customers without a card or wallet balance can buy physical goods on the platform instead of only through WhatsApp.
+ Cash orders never enter the online payment recovery machinery, so it needs no special cases.
- **Goods are made before they are paid for.** A refused COD order wastes material and printer time. Mitigated by the limits in decision 6, the refusal block, the contact phone, and the admin's right to cancel an unpaid line at any time. Recorded in the risk register.
- **The courier holds the business's cash** between delivery and remittance. Settling up with the courier is outside the platform.
- **"Start printing" is now the only production cutoff and the customer never sees it.** Self-cancel closes when the administrator marks it, so started work is protected only if it is marked promptly.
- **One cash handover per order,** so a cash order's lines are delivered together; a partly refused order is resolved by cancelling the refused line first.
- The order projection gains a branch: an unpaid cash order is `in_progress` (or `cancelled` once every line is), and the API exposes `payment_due`.
- `free_shipping_threshold` is already seeded by VS-007 (migration `de1d8a23512f`); VS-028 deletes the row and its registry entry. No order, payment or zone table exists yet, so nothing else in code changes.

## Alternatives rejected

- **A `pending` cash payment row from checkout** — would be expired by the checkout hold, queried by reconciliation and retried by the customer, and its amount would be wrong after a line is cancelled.
- **Recording cash per line** — several paid payments per order would break one-live-payment (INV-19) and the exact-amount check.
- **COD for mixed or STL orders** — an emailed file cannot be recovered from a customer who then refuses to pay.
- **Keep zones as an informational fee estimate** — the courier sets the fee; a platform estimate would be wrong and still read as a promise.

## Revisit when

Refusal rates make COD unprofitable, a courier offers an API with fee quotes or tracking, or the business wants to charge delivery itself. Charging shipping again would need a new ADR.
