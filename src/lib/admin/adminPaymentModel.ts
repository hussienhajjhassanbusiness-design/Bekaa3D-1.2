import type { StatusBadgeTone } from "@/components/admin/StatusBadge";
import type { PaymentStatus } from "@/lib/payment/paymentStatusModel";

// #ARCHITECTURE-ADMIN-PAYMENT-ADAPTER
//
// Reuses FVS-027's PaymentStatus directly — never a second,
// incompatible payment-status union. If the admin lifecycle ever
// needs additional states, they are added through this adapter once
// the backend confirms them (FVS-028-IMPLEMENTATION-PLAN.md §0/T01).
//
// #SECURITY-PAYMENT-OPERATIONS-DATA — no provider secret, webhook
// signature, raw provider payload, credential, or internal
// reconciliation detail exists on this type at all.
//
// `canManualConfirm`/`manualConfirmBlockedReason` are the server-
// authoritative capability this slice's gating relies on — never a
// locally-computed allowed-status matrix.
export interface AdminPaymentModel {
  id: string;
  status: PaymentStatus;
  amountCents: number;
  currency: string;
  providerDisplayLabel: string;
  providerReferenceDisplayValue: string;
  linkedOrderDisplayId: string;
  canManualConfirm: boolean;
  manualConfirmBlockedReason?: string;
}

const DESCRIPTORS: Record<PaymentStatus, { label: string; tone: StatusBadgeTone }> = {
  pending: { label: "Pending", tone: "neutral" },
  processing: { label: "Processing", tone: "neutral" },
  paid: { label: "Paid", tone: "positive" },
  failed: { label: "Failed", tone: "negative" },
  expired: { label: "Expired", tone: "warning" },
};

export function describeAdminPaymentStatus(status: PaymentStatus): { label: string; tone: StatusBadgeTone } {
  return DESCRIPTORS[status];
}
