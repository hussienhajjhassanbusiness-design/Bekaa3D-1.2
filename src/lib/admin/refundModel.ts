// #SECURITY-REFUND-SETTLEMENT-SEPARATION
//
// Frontend-normalized, admin-facing refund shapes only — never a
// claim about RefundDetail/Page's real field names (unconfirmed,
// FVS-032-IMPLEMENTATION-PLAN.md §0). No provider secret, raw
// webhook payload, or credential exists on this type at all.
//
// `isSettled` is an explicit, caller-supplied capability — never
// derived from `statusLabel` text. A refund record can exist (have
// an id, an amount) without money having moved; this field is the
// only thing any component may use to distinguish "created" from
// "settled" — never the presence of `id` alone.
export interface RefundLineBreakdownModel {
  lineId: string;
  productDisplayName: string;
  amountCents: number;
  currency: string;
}

export interface RefundModel {
  id: string;
  linkedOrderDisplayId: string;
  statusLabel: string;
  isSettled: boolean;
  totalAmountCents: number;
  currency: string;
  settlementMethodLabel?: string;
  lines?: readonly RefundLineBreakdownModel[];
  shippingAmountCents?: number;
  reason?: string;
  createdAtLabel?: string;
}
