# Backend handoff: a pending reissued refund cannot be voided once its line is `refunded`

**Status:** open question for the backend team. No frontend workaround exists or is planned.
**Backend:** `C:\My projects\Bekaa3D-backend`, branch `main`, commit `2dfb27b`.
**Found:** Phase 5I real-backend acceptance (2026-11-11); verified against the implementation in Phase 6A.

## What happened (real run)

Order `B3D-WQMG40BW` (online, mock provider, paid $36.00; one physical line, 2 × dragon, delivered):

1. Admin refund $5.00 → **settled**.
2. Admin refund $31.00 (the rest) → **failed** (stays owed).
3. Reissue of (2) → a new refund $31.00, **pending**. The failed one is no longer owed (`reissued_by_refund_id` set).
4. `POST /api/v1/admin/refunds/{reissued_id}/void {reason}` →
   **`409 INVALID_STATE_TRANSITION`**, `reason: "line_already_refunded"`.

Database after (4): the order line's `fulfillment_status` is `refunded`; the reissue is still `pending`.

## Why (implementation)

- `payments/application/services/refunds.py` `void_refund`: collects the states of the lines the refund names and passes `line_refunded=OrderItemStatus.REFUNDED in touched` to `_decide`.
- `payments/domain/refunds.py` `refund_step(..., RefundAction.VOID)`: after `voided` (no-op), `settled` (refused) and `reissued` (refused), it refuses with `LINE_ALREADY_REFUNDED` whenever `line_refunded` is true. The docstring states the intent: *"A void never reopens a closed line: its balance is 0 by state, so the money would be stranded."*
- The line became `refunded` as soon as the open refunds (settled $5 + pending $31) covered its full total, so the pending reissue now counts as "closing" the line.

So this is **intended behaviour by the current rule (VS-030 U16)**, not an accidental bug. Its consequence is the question below.

## Expected vs actual

| | Expected (by an operator) | Actual |
|---|---|---|
| Void a **pending** refund recorded by mistake | allowed; the line's balance comes back | refused with `line_already_refunded` if that refund (with others) covers the whole line |
| The only remaining paths for that refund | settle, or fail (stays owed) | settle, or fail; a failed one cannot be voided either for the same reason, so an obligation recorded by mistake can never be closed unpaid |

## Question for the backend team

Should a void of a **pending** (never paid) refund be allowed to reopen its line (`refunded` → the previous state, balance restored), at least when the refund being voided is the one that closed the line? If not, what is the supported way to correct a refund recorded by mistake for a full line?

## Frontend behaviour (unchanged, intentional)

- `/admin/refunds/[id]` offers Void on a pending or failed-and-owed refund (the documented state machine); the server decides.
- On this refusal the dialog stays open with frontend copy ("One of these items is already fully refunded."), the refund is re-read, and nothing is changed or fabricated locally.
