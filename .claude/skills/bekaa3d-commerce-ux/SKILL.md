---
name: bekaa3d-commerce-ux
description: Use when building or reviewing any Bekaa3D cart, checkout, payment-result, product-detail, STL, offer/negotiation, or order-status UI, to apply the correct physical-vs-STL product rules, mixed-cart behavior, server-authoritative totals, backend-verified payment status, and real offer/order state machines instead of assuming conventional single-product-type e-commerce behavior.
---

# Bekaa3D Commerce UX

## Overview

Bekaa3D sells two fundamentally different product types — physical 3D-printed goods and digital STL files — often in the same cart and order. Most e-commerce UI intuition (finite inventory, one product type, "payment succeeded" from a redirect, real-time status via WebSockets) is **wrong here by default**. This skill encodes the domain rules that make Bekaa3D's commerce UI different from a generic storefront template.

**REQUIRED BACKGROUND:** `bekaa3d-api-contract` — this skill tells you *what* the domain rules are; that skill tells you how to verify the exact request/response shape before building against it.

## When to Use

Any UI touching: product detail (physical or STL), cart, checkout, payment result/return pages, order history/detail/status, offers/negotiation, entitlements, or downloads.

## Physical vs. STL — What Differs

| Aspect | Physical | STL |
|---|---|---|
| Fulfillment | Shipping or pickup; has production/delivery states | Instant entitlement + download, no shipping |
| Cart quantity | Steppable, capped by a server-side max | **Always 1** — never render a quantity stepper for an STL line |
| Ownership check | N/A | Already-owned STL is never addable to cart — check entitlement before offering "add to cart" |
| Availability | Can be "unavailable" (still listed) or WhatsApp-only (no cart action at all) | Doesn't go "out of stock" the same way — availability is about entitlement/version, not inventory |
| Cancellation | Customer can self-cancel **pre-production only**; admin can cancel post-production (refund obligation) | **Never self-cancellable** — a completed digital sale doesn't "un-ship" |
| Post-purchase surface | Order tracking/delivery status | Library + download history + download cap |
| Negotiable | No offer flow | Yes — Make an Offer flow, subject to floor/cooldown/deadlines |

**Do not assume conventional finite inventory** for physical products unless a specific backend slice defines stock quantities — the backend plan (VS-011) explicitly states products have no stock-quantity field in V1.

## Mixed Carts

A cart may hold both types at once. Rules that must hold everywhere a cart/order is rendered:

- Each line is independently addressable — never collapse a mixed order into one blended status. A physical line "in production" and a digital line "delivered" coexist in the same order and must both be visible with their own state.
- Delivery method (shipping address+zone, or pickup) applies to physical lines; digital lines need explicit **digital final-sale consent**, captured separately from shipping terms.
- Price snapshots: cart/checkout/order always display the price that was locked in at that step, not the current catalogue price. If they differ, show that explicitly ("price updated" note) — never silently reconcile or silently ignore the difference.

## Totals Are Never Client-Computed

**The backend is the sole authority for:** prices, discounts, totals, tax, shipping cost, product availability, order state, offer state, payment state, permissions, entitlements, and STL download permission.

The frontend may show a client-side *estimate* only where it can exactly mirror a known, public, stable server rule (e.g., a free-shipping threshold already exposed via public settings) — and must clearly label it as an estimate until the server confirms. Any checkout/cart/offer screen that computes and displays a "final" total without it coming from a server response is a bug, not a convenience.

## Payment UX — The One Rule That Matters Most

**Redirect query parameters, browser return pages, and client-side flags are never proof of payment success.** After a checkout redirect back to the site, the only correct sequence is:

```
Return to site → identify the order from the URL → poll the backend's own
verified payment/order status → render pending/success/failed/expired based
on THAT response → stop polling on a terminal state or a bounded timeout
```

A page that renders "Payment Successful" because `?status=success` was in the URL is the single worst mistake possible in this codebase — it can show a customer a false confirmation for a payment that the backend independently rejects moments later via webhook/reconciliation. Every payment-result screen needs an explicit **pending/verifying** state that is the default on load, not a flash before success.

## Offer / Negotiation UX

Offers have real backend-defined mechanics — render exactly these, never a simplified approximation:

- **Turn-based**: only the party whose turn it is can act (counter/accept/reject); render only the actions legal for the current turn, not a static action bar.
- **Deadlines**: each round has a deadline; show a live countdown, but treat the *server's* rejection of an expired action as authoritative — a client-side clock can drift or the user can reload mid-countdown.
- **Cooldown**: a rejected offer arms a cooldown before the same customer can re-offer on that product; surface the specific reason, don't just say "try again."
- **History**: rounds are append-only — never edit or remove a past round from the displayed timeline, even after acceptance/rejection.
- **No invented realtime.** Do not add WebSocket/SSE/push behavior for offers (or anything else) unless a specific backend slice defines it. Use polling / refetch-on-focus for "live-looking" freshness instead.

## Order / Line State UX

- Render only the actions/transitions that are legal from an order line's *current* state — never a generic status dropdown or free-text status field.
- STL lines and physical lines have different legal transitions (see table above) — a shared `OrderLineItem` component must branch on type, not apply one state machine to both.
- A customer never sees another customer's or an admin-only view of an order (internal notes, admin-only fields) — these are two different response shapes/components, not one component with fields conditionally hidden by CSS or a client-side role check (see `bekaa3d-api-contract` for why hiding ≠ authorization).

## STL Delivery

Never construct, guess, or persist a raw storage path/private URL for an STL (or any privately-stored) file. Always link through the backend's authorized delivery endpoint, and treat a download link as a plain, authenticated `href` (not a JS-mediated blob fetch) so native browser Range/resume support isn't broken for large files.

## Common Mistakes

| Mistake | Reality |
|---|---|
| Quantity stepper on an STL cart line | STL quantity is always 1 — no stepper, ever. |
| "Payment Successful" rendered from a URL param | Always poll verified backend status first; default state is "verifying." |
| One blended status badge on a mixed order | Each line has its own state; render per-line. |
| Client computes final checkout total | Only the server's response is the final total; client figures are estimates at best. |
| Building a WebSocket for "live" offer updates | Not in the backend contract — use polling/refetch-on-focus. |
| Treating a rejected offer as a permanent block | It's a cooldown, not a ban — surface the specific reason/duration. |
| Physical product shown as "out of stock" from a client-tracked counter | No stock-quantity field exists in V1; availability comes from the server's own field, not an inferred count. |
| Hiding an admin-only field with CSS in a shared component | Authorization is a backend + separate-response-shape concern, never a frontend hiding trick (see `bekaa3d-api-contract`). |
