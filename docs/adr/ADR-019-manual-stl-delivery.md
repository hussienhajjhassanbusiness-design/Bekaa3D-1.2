# ADR-019: Deliver purchased STL files manually by email; the platform stores no STL files

**Status:** Accepted
**Date:** 2026-10-06
**Source basis:** Business decision by the owner, 2026-10-06; SRS §1, §3, §5, §9, §10, §20.3, §21, §24
**Supersedes:** [ADR-014](ADR-014-entitlements-and-protected-downloads.md) in full; the `downloads` half of [ADR-015](ADR-015-partition-high-volume-logs.md)

## Context

ADR-014 designed automated STL delivery: the administrator uploads versioned file bundles, a payment grants an Entitlement, and the customer downloads through nginx `X-Accel-Redirect` with logging, a daily cap and monthly statistics. That is four vertical slices (VS-017, VS-018, VS-019, VS-042), a private storage volume, malware scanning of large files, a partitioned high-volume table and nginx coordination, before the first STL can be sold.

The business does not want it. The owner keeps the STL files on the administrator's own drive and, after each verified purchase, emails the file to the customer by hand. The platform's job is to take the order and payment safely, and to tell the administrator exactly what to send, to whom, and what is still outstanding.

## Decision

1. **No STL file is stored on, uploaded to, or served by the platform.** No asset versions, STL assets, entitlements, downloads, download log, download cap or download statistics.
2. **A paid STL line waits for manual delivery.** When payment verification succeeds, each STL `OrderItem` moves to `awaiting_delivery` in the same transaction (replacing "entitlement granted").
3. **The administrator delivers by email attachment** from their own mailbox to the customer's verified account email. The order records that address at checkout (`customer_email_snapshot`), so the administrator sends to the address the customer bought with.
4. **The administrator marks the line delivered** from the STL delivery queue: `awaiting_delivery → delivered`, recording who marked it and when, audit-logged, and the customer is notified in-app and by email ("your STL file has been sent"). The queue lists every STL line awaiting delivery, oldest first.
5. **Ownership is a paid, unrefunded STL line.** It replaces the active entitlement everywhere it was used: blocking a repeat purchase of the same STL and the Verified Purchase badge. A partial unique index on `order_items` allows one live STL line (`pending`, `awaiting_delivery` or `delivered`) per customer and product, so two parallel checkouts cannot both buy the same STL (database-design §8.4).
6. **Re-sending is outside the system.** A customer who lost the file asks through the contact form or WhatsApp and the administrator re-sends it. The platform records only the first delivery.
7. **Refunds.** Refunding an STL line marks it `refunded`. A line refunded while still `awaiting_delivery` leaves the delivery queue and must not be sent. A line refunded after delivery cannot be recalled; the protections are the recorded all-sales-final consent and the delivery record.
8. **Bounded contexts.** Digital Assets is removed. STL line delivery state belongs to Fulfillment, next to physical line fulfillment.

## Consequences

+ Four slices and the riskiest infrastructure (private file volume, nginx internal location, large-file malware scanning, a partitioned log) leave V1.
+ No STL master can leak from the server, because none is there.
+ One fulfillment model for both product types: a paid line waits in an admin queue until a person completes it.
- **Delivery is no longer instant.** The customer waits for the administrator. The storefront and checkout must say so, and the promised delivery time is an open decision (SRS §30).
- **Email attachment limits** (commonly about 20–25 MB) can be smaller than an STL bundle. The administrator may need to compress files or send a cloud-storage link; the platform does not control this. Recorded in the risk register.
- **The administrator's drive is the only copy** of the STL files. Backing it up is the business's responsibility, outside the platform.
- No download statistics: the "most downloaded" sort and `products.download_count` are dropped, and the "most downloaded" report becomes "best-selling STLs", computed from paid lines (VS-043).
- Leftovers from already-built slices are removed by VS-023b: the seeded `daily_download_cap` setting, the empty `src/app/digital_assets` package, and stale VS-019 references in code comments. The `download` notification type stays as the category for the "STL sent" event, so no enum migration is needed.
- Slices VS-017, VS-018, VS-019 and VS-042 are removed; VS-023b (delivery queue) is added; nginx and the client-IP fix move to VS-020.

## Alternatives rejected

- **Keep ADR-014 and also allow manual delivery** — builds and maintains the whole download stack for a path the business will not use.
- **Store files on the platform, deliver manually** — keeps the storage, scanning and backup burden without the benefit of self-service downloads.
- **No delivery tracking** — the administrator would have no list of what is still owed, and the customer no confirmation it was sent.

## Revisit when

Sales volume makes manual sending a bottleneck, delivery delays cause refunds or complaints, or STL bundles routinely exceed what email can carry. Automated delivery would then need a new ADR; ADR-014 is the starting point.
