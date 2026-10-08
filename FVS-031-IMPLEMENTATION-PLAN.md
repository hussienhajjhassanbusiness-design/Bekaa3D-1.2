# FVS-031 — Order Cancellation & Returns UX — Implementation Plan

**Backend:** VS-025. **Frontend deps:** FVS-029, FVS-030.

## §0 Audit findings

- VS-025 (`vertical-slice-plan.md:454-469`) confirms, in prose only: customer may
  cancel paid physical work pre-production only; STL never self-cancellable;
  admin cancellation after production follows a refund-obligation path; shipped
  can become returned; returned can re-ship/reprint/refund **via the existing
  line-transition endpoint** (not a new endpoint); same-line locking so
  production-start vs. self-cancel has one winner.
- **No literal endpoint path, request body, or response schema exists anywhere**
  for customer cancel or admin cancel. Both are NEEDS BACKEND CONFIRMATION.
  Returns/re-ship/reprint/refund explicitly reuse "the existing line transition
  endpoint" — i.e. the same mechanism FVS-030 already built
  (`AdminOrderLineModel.availableActions`), not a new one.
- **No fulfillment status vocabulary/state diagram is confirmed** (same gap
  FVS-030 already recorded). Therefore every example status in this plan and
  in the governing prompt (paid/production/returned) is illustrative only,
  never a literal comparison anywhere in code.
- FVS-030 already established the correct architecture for "which actions are
  currently legal": `TransitionAffordance {id, label, requiresConfirmation}`,
  rendered verbatim by `TransitionActions`, composed per-line in
  `AdminOrderLine`. Cancellation and returned-item actions are the **same
  shape** — this plan reuses that architecture rather than inventing a second
  one, per the governing rule `#SECURITY-SERVER-CANCELLATION-AUTHORITY`.
- **Returned-item actions (T05) need no new component.** VS-025 states
  re-ship/reprint/refund flow through the existing line-transition endpoint —
  the exact mechanism `AdminOrderLine`'s `availableActions` already models.
  Building a parallel `ReturnedItemActions` component would duplicate
  `TransitionActions` byte-for-byte and risk drifting out of sync. This is
  recorded as an explicit reuse decision, not a gap.
- **Customer cancel and admin cancel are each their own endpoint** (per VS-025's
  own wording: "Customer order cancel; admin order cancel; existing line
  transition endpoint handles returned/re-ship/reprint") — so unlike returns,
  these two genuinely need their own presentation seams.

## §1 Architecture decision: extract the shared affordance primitive

FVS-030's `TransitionActions` (admin-only) and this slice's customer cancel
button need identical logic: render exactly the supplied legal action(s),
open `ConfirmDialog` only when `requiresConfirmation` is true, disable while
pending, render nothing when there is no legal action. A customer-side
component importing from `src/components/admin/` would invert the
established dependency direction (admin depends on customer order primitives,
never the reverse). This is the second genuine reuse case that justifies
extraction, mirroring this engagement's established "extract on second reuse"
discipline (`NotFoundContent`, `OrderSummaryDisplay`):

- `src/lib/orders/orderActionModel.ts` — `OrderActionAffordance {id, label,
  requiresConfirmation}`, the neutral, domain-free shape (moved out of
  `adminOrderModel.ts`, which re-exports it as `TransitionAffordance` for
  zero behavior change to existing imports).
- `src/components/feedback/OrderActionButtons.tsx` — the rendering logic
  moved out of `TransitionActions.tsx`, which becomes a thin wrapper
  preserving its exact existing name/props/behavior (re-verified against its
  own untouched 7-test file).

Marker: `#ARCHITECTURE-SERVER-PROVIDED-ORDER-ACTIONS` (continuity with
FVS-030) and `#ARCHITECTURE-ORDER-EXCEPTION-ACTIONS` (this slice's extension).

## §2 Task list

- **T01** — `orderActionModel.ts` (+test); `adminOrderModel.ts` edit
  (re-export + additive `adminCancelAction?`/`refundObligationMessage?`
  fields); `orderExceptionModel.ts` (+test) with `CancellableOrderLineModel`
  and `resolveCustomerCancelAction()`. CAN IMPLEMENT NOW.
- **T02** — `OrderActionButtons.tsx` (+test, extracted); `TransitionActions.tsx`
  (edit, thin wrapper, zero behavior change); `CancelOrderLineButton.tsx`
  (+test). CAN IMPLEMENT NOW.
- **T03** — folded into T02: `CancelOrderLineButton` takes an `errorMessage?`
  prop (same established pattern as `InternalNoteEditor`/`ManualConfirmDialog`)
  for the race-lost/generic-failure text. No separate feedback component —
  avoids inventing a parallel taxonomy.
- **T04** — `AdminCancelDialog.tsx` (+test), mirroring `ManualConfirmDialog`'s
  DialogShell + reason-textarea + whitespace-validation pattern exactly.
  CAN IMPLEMENT NOW.
- **T05** — no new component (§0). Added test coverage proving
  `AdminOrderLine`'s existing `availableActions` architecture already renders
  caller-supplied re-ship/reprint/refund-labeled affordances with no special
  casing.
- **T06** — `CancellableOrderLine.tsx` (+test, customer composition, mirrors
  `AdminOrderLine`'s structure: `OrderLineItem` + `CancelOrderLineButton`);
  `AdminOrderLine.tsx` edit (additive `onAdminCancel`/`isCancellingLineId`
  props, owns its own `AdminCancelDialog` instance exactly as it already owns
  nothing extra — mirrors how `TransitionActions` owns its own
  `ConfirmDialog`). CAN IMPLEMENT NOW.
- **T07** — refund-obligation presentation: satisfied by T01's
  `refundObligationMessage?` field + T04's rendering of it. No separate file.
- **T08** — real mutations. BLOCKED (no endpoint confirmed).
- **T09** — real integration into order routes + E2E. BLOCKED (T08 + FVS-029/030
  route gates).
- **T10** — backend acceptance. Pending (see questions below).

## §3 Explicit non-goals (DO NOT IMPLEMENT)

Guessed endpoints; guessed status literals; a hardcoded pre-production
transition table; a hardcoded returned-state machine; optimistic
cancellation; refund-amount computation; automatic refund creation; STL
authorization based only on the frontend; real order-route integration; fake
E2E against a non-existent backend flow.

## §4 Canonical cache-invalidation intent (documented, not implemented)

Once a real cancel/transition mutation exists, success must invalidate
`orderKeys.detail(orderId)` (customer) and the relevant admin order read —
never a locally-mutated status. This batch implements no mutation, so there
is nothing to invalidate yet; this section exists so T08/T09 do not
rediscover the rule.

## §5 Backend questions (unresolved only — see full report for the complete list)

Exact customer-cancel and admin-cancel endpoints/bodies; exact
capability/status representation on order detail; exact race-lost HTTP
status/problem code and whether the server returns refreshed state; exact
refund-obligation representation; exact returned-state action ids this slice
must eventually map to approved labels for. Full enumeration in the final
report.
