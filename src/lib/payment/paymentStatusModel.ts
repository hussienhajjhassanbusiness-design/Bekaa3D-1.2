// #ARCHITECTURE-PAYMENT-STATUS-ADAPTER
//
// Frontend-normalized concepts only — never a claimed backend enum
// literal (FVS-027-IMPLEMENTATION-PLAN.md §0/§1: no dedicated status
// endpoint or response schema is confirmed anywhere).
export type PaymentStatus = "pending" | "processing" | "paid" | "failed" | "expired";

const TERMINAL_STATUSES: readonly PaymentStatus[] = ["paid", "failed", "expired"];

export function isTerminalPaymentStatus(status: PaymentStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}

// The critical structural guarantee: a local polling outcome
// ("timeout"/"network-error") can never be represented as a backend
// PaymentStatus value — there is no `status` field on either variant,
// so nothing downstream can accidentally treat "we stopped checking"
// as "the payment failed."
export type PaymentVerificationState =
  | { kind: "verifying" }
  | { kind: "status"; status: PaymentStatus }
  | { kind: "timeout" }
  | { kind: "network-error" };
