# FVS-032 — Admin Refund Management — Implementation Plan

**Backend:** VS-026. **Frontend deps:** FVS-030, FVS-031.

## §0 Audit findings

- VS-026 (`vertical-slice-plan.md:471-486`) gives schema *names* only
  (`RefundCreate`, `RefundDetail/Page`, `RefundSettlementRequest`) with no
  field enumeration. The four placeholder endpoints the governing prompt
  lists (`POST /admin/orders/{id}/refunds`, `GET /admin/refunds`,
  `GET /admin/refunds/{id}`, `POST /admin/refunds/{id}/settle`) have **no
  literal source evidence anywhere** — all NEEDS BACKEND CONFIRMATION.
- VS-026's logic bullet **does** state the refund-affects-entitlement policy
  directly: "digital refund revokes entitlement." The policy itself is
  therefore confirmed; the exact *moment* (creation vs. settlement) is not —
  copy and architecture below never claim a moment.
- VS-026 also confirms: "server derives refundable balances" (→ rule
  `#SECURITY-SERVER-REFUND-BALANCE-AUTHORITY`); "obligation remains pending
  until settlement" (→ rule `#SECURITY-REFUND-SETTLEMENT-SEPARATION`);
  "provider/manual method" (→ two settlement methods exist, no field shape
  given); "selected line amounts + shipping" (→ refund creation is
  per-line + optional shipping, never a single order-level amount).
- **List-schema confidence for a refund queue** is comparable to FVS-028's
  `AdminPaymentList`, not FVS-030's deferred admin-order queue: VS-026's own
  text yields the same tier of concepts FVS-028 used (status, amount,
  method, order linkage) even though no field is named literally. Decision:
  build `RefundQueue` via `AdminTable`, mirroring `AdminPaymentList`'s
  columns exactly, rather than deferring.
- No settlement-status vocabulary is confirmed (no equivalent of FVS-027's
  real `PaymentStatus` union exists for refunds) — status is a caller-
  supplied `statusLabel` plus an explicit `isSettled: boolean` capability,
  mirroring `OrderLineModel.statusLabel`'s precedent, never a typed status
  enum.
- `useCheckoutAttempt.ts` (`src/lib/checkout/`) is already fully
  domain-free in implementation (a lazy-UUID attempt key + explicit
  `startNewAttempt()`) — only its name/location are checkout-specific. This
  is the second genuine reuse case (refund creation needs the identical
  primitive) that justifies extracting it to a neutral location, mirroring
  this engagement's established extraction discipline.

## §1 Task list

- **T01** — `src/lib/admin/refundKeys.ts` (+test, mirrors `entitlementKeys`
  exactly: `root`/`list()`/`detail(id)`); `src/lib/admin/refundModel.ts`
  (+test: `RefundModel`, `RefundLineBreakdownModel`);
  `src/lib/admin/refundCreateModel.ts` (+test: `RefundLineCandidate`,
  `ShippingRefundCandidate`, `validateRefundLineAmount()`). CAN IMPLEMENT NOW.
- **T02** — `RefundCreateForm.tsx` (+test): per-line `MoneyInput` reuse,
  server-ceiling validation, optional shipping candidate, submit-disabled
  guard. Folds in **T03** (ceiling validation, via T01's pure helper) and
  **T04** (digital-revocation confirmation, via an internal `ConfirmDialog`
  — no separate component, mirrors FVS-031's T03/T05 folding precedent).
  CAN IMPLEMENT NOW.
- **T05** — `RefundDetail.tsx` (+test). CAN IMPLEMENT NOW.
- **T06** — `RefundQueue.tsx` (+test), `AdminTable` composition mirroring
  `AdminPaymentList`. CAN IMPLEMENT NOW (see §0 evidence tier decision).
- **T07** — `SettleRefundDialog.tsx` (+test), mirroring
  `ManualConfirmDialog`'s DialogShell + explicit-acknowledgment pattern
  (no reason field — VS-026 does not mention one for settlement).
  CAN IMPLEMENT NOW.
- **T08** — `src/lib/shared/useIdempotencyAttempt.ts` (+test, extracted from
  `useCheckoutAttempt.ts`, which becomes a thin wrapper, zero behavior
  change re-verified); `RefundCreateForm`'s `isSubmitting`-disables-submit
  guard (part of T02) is the structural duplicate-submission guard for
  this batch. No speculative header/body idempotency transport is built.
  CAN IMPLEMENT NOW.
- **T09** — real API/query/mutations. BLOCKED (no endpoint/schema confirmed).
- **T10** — routes + admin integration + E2E. BLOCKED (FVS-005 + T09).
- **T11** — backend acceptance. Pending.

## §2 Explicit non-goals (DO NOT IMPLEMENT)

Guessed endpoints/DTOs/status literals; a refund ceiling derived from order
price; shipping refund derived locally; automatic full-order refund;
automatic digital entitlement revocation (client-side); client-side
money-settled state; provider API/secrets; guessed settlement body/
idempotency header; unprotected admin routes; fake mandatory E2E against a
non-existent backend flow.

## §3 Cache-relationship intent (documented, not implemented)

Once real mutations exist, a successful refund-create/settle must
invalidate `refundKeys` and `orderKeys.detail(orderId)`/`orderKeys.list(...)`,
and — only for a digital line whose refund the backend confirms revokes
entitlement — `entitlementKeys.root`. No broad "invalidate everything"
behavior. This batch implements no mutation, so nothing is invalidated yet;
recorded so T09 does not rediscover the boundary.
(`#ARCHITECTURE-REFUND-ENTITLEMENT-BOUNDARY`)

## §4 Backend questions (unresolved only — full enumeration in the final report)

Exact endpoint paths for all four operations; exact refundable-balance
field names/location; exact `RefundCreate`/`RefundDetail`/`RefundPage`/
`RefundSettlementRequest` field shapes; exact over-refund error
shape/status; exact settlement request body and manual-vs-provider
distinction; exact idempotency header/key format; exact moment of digital
entitlement revocation (creation vs. settlement).
