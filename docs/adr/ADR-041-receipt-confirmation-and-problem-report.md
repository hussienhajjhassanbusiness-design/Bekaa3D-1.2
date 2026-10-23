# ADR-041: Receipt confirmation and problem report - physical lines only, first timestamp kept, a report is a linked contact message that alerts every administrator in the same transaction (VS-029b)

**Status:** Accepted
**Date:** 2026-10-23
**Source basis:** [VS-029b slice plan](../vertical-slice-plan.md#vs-029b--receipt-confirmation-and-problem-report); SRS §8.8, §15.2, BR-147, F-069; FR-21; database-design.md §12.6 and `order_items`; glossary "Receipt Confirmation", "Problem Report"; [ADR-024](ADR-024-cash-on-delivery-and-courier-priced-shipping.md) d9, d10 and its open question for VS-029b / VS-033; [ADR-026](ADR-026-captcha-refusal-and-outage.md); [ADR-030](ADR-030-bring-your-idea-submission.md); [ADR-040](ADR-040-admin-order-queue-fulfillment-and-cash-handover.md)
**Answers:** ADR-024's open questions "Is receipt confirmation physical-only?" and "`contact_messages.order_id` belongs to neither VS-033 nor VS-029b explicitly".
**Applies first to:** `POST /api/v1/me/orders/{order_id}/confirm-receipt`, `POST /api/v1/me/orders/{order_id}/report-problem`; migration `0f43e238eaae`.

## Context

The delivered and picked-up emails (VS-029) carry "I got it" and "Report a problem" buttons that only open the order page, because email scanners follow links. The documents disagreed on which lines these actions cover: database-design.md and the glossary say "physical only", while SRS §8.8, FR-21 and the API row say "delivered / picked-up lines", which would include a delivered STL line. `contact_messages` (VS-033) had no `user_id` or `order_id`, and nothing told the administrator that a report had arrived other than the contact queue itself.

## Decision

1. **Physical lines only.** Both actions cover the order's physical lines in `delivered` or `picked_up` (`ordering/domain/receipt.py`). An STL `delivered` means the file was emailed (ADR-019), not received, so it is never stamped. An order with no such line refuses both actions with `409 INVALID_STATE_TRANSITION`, `reason: no_delivered_line`; that includes an order whose only delivered line is an STL. The check `ck_order_items_feedback_physical_only` keeps both timestamps null on STL lines.
2. **The first timestamp is kept.** Each action sets its timestamp only where it is null (`UPDATE … WHERE … IS NULL RETURNING id`), so a repeat or a concurrent duplicate changes nothing (FR-21: "Confirming twice keeps the first confirmation"). A line that becomes delivered later is stamped by the next confirmation. The UPDATE repeats the rule (same order, physical, `delivered` / `picked_up`), so a wrong id list can never stamp another order's line. The time is read once the locks are held. `order.receipt_confirmed` is audited only when a line was stamped. Every report is audited as `order.problem_reported` with the stamped line ids and the message id, never the message body.
3. **A report is a contact message linked to the order.** VS-029b owns `contact_messages.user_id` and `order_id` (nullable, partial indexes; `user_id` `ON DELETE SET NULL` and `order_id` `RESTRICT`, as database-design.md §14 says). A user with a linked report owns that order, and `orders.user_id RESTRICT` already stops that user being deleted, so the check below cannot be broken by a delete. `ck_contact_messages_order_has_user` makes an order link require a user. The message's email is the account email. Its name is the order's `recipient_name`, or the email's local part when there is none (pickup orders); the full email could break the 100-character name check. Its subject is "Problem with order {order_number}" and its phone is null, because the order already has it. Each report is a new message in the VS-033 queue, as repeated contact-form messages are. No captcha, because the caller is signed in. `ContactMessageDetail` gains `user_id` and `order_id`.
4. **Every active administrator is notified in the same transaction (owner decision).** The report inserts one in-app notification per active administrator: type `order`, event `order.problem_reported`, with `order_id`, `order_number`, `contact_message_id` and the title "Problem reported on order {order_number}". The notification never carries the message body, email or phone. Unlike VS-034 (ADR-030), a failed notification fails the whole report, so the message, its notifications, the stamps and the audit row commit together or not at all. A refused report notifies nobody.
5. **Lock order and boundaries.** Both routes lock the caller's `orders` row (the ownership predicate is in the lock, so another customer's order is the same 404 as an unknown id and is never locked), then its lines by id, and take no other row lock (ADR-024 d9). Neither changes `fulfillment_status`, `orders.status` or the status history. Ordering reaches Engagement only through `app.engagement.public.submit_problem_report`.
6. **Limits.** CSRF is checked before the limit. The report is limited to 5 an hour per user, the same as the contact form's per-email limit. Confirmation is idempotent and has no limit. The message is 1-5000 characters after trimming, line breaks allowed, with no control characters.

## Consequences

+ The order completes without either action, and nothing about the order's state depends on them (BR-147).
+ The administrator sees the timestamps on `AdminOrderDetail` lines and the report in the contact queue with its `order_id`, and gets an in-app alert.
- A second report does not move `problem_reported_at`; the later reports are visible only in the contact queue.
- An outage of the notifications table now blocks problem reports, which the owner accepted in return for atomicity.
- VS-044 (data export) and VS-045 (anonymisation) must include the contact messages that carry `user_id`. A report's foreign keys take `FOR KEY SHARE` on `users` rows under the orders lock, so VS-045 must lock orders before it updates a user's unique key.

## Alternatives rejected

- **Covering delivered STL lines** - the customer cannot "receive" a file the administrator emailed from their own drive, and database-design.md defines both columns as physical only.
- **Moving `problem_reported_at` on every report** - it would hide when the problem was first raised, and the queue already keeps every report.
- **Notifying in savepoints so a failure keeps the report (the VS-034 pattern)** - the owner chose one all-or-nothing transaction.
- **A composite foreign key proving the message's user owns the order** - it would need a new `UNIQUE (orders.id, user_id)`; the user id comes from the locked, owned order row, and ownership never changes.
