import type { ApiError } from "@/lib/api/ApiError";
import { readProblemString } from "@/lib/api/problemExtensions";
import type { StatusDescriptor } from "@/lib/orders/orderStatus";
import type { AdminOrderDetailDTO, AdminOrderLineReadDTO, CancelReason } from "./adminOrderTypes";

// #FVS030-ADMIN-ORDER-PRESENTATION (phase 5H)
//
// Frontend-owned wording for the administrator's order screens, and the
// two order-level offers the backend exposes no flag for. Every lookup is
// an own-property check: an unknown enum value degrades to neutral text,
// never the raw value. Line transitions are NEVER derived here: a line's
// buttons are exactly its server-provided `available_actions`.

const UNKNOWN: StatusDescriptor = { label: "Status unavailable", tone: "neutral" };

function lookup<T>(table: Readonly<Record<string, T>>, key: string): T | undefined {
  return Object.prototype.hasOwnProperty.call(table, key) ? table[key] : undefined;
}

// The real line states (an administrator sees in_production, unlike a customer).
const LINE_STATUS: Readonly<Record<string, StatusDescriptor>> = {
  pending: { label: "Pending", tone: "warning" },
  in_production: { label: "In production", tone: "neutral" },
  ready_to_ship: { label: "Ready to ship", tone: "neutral" },
  shipped: { label: "Shipped", tone: "neutral" },
  delivered: { label: "Delivered", tone: "positive" },
  returned: { label: "Returned", tone: "warning" },
  ready_for_pickup: { label: "Ready for pickup", tone: "neutral" },
  picked_up: { label: "Picked up", tone: "positive" },
  cancelled: { label: "Cancelled", tone: "negative" },
  refunded: { label: "Refunded", tone: "neutral" },
};

// STL lines: emailed by hand (ADR-019). No upload, download or entitlement.
const STL_LINE_STATUS: Readonly<Record<string, StatusDescriptor>> = {
  awaiting_delivery: { label: "Awaiting email delivery", tone: "warning" },
  delivered: { label: "Sent by email", tone: "positive" },
};

export function describeAdminLineStatus(status: string, productType: string): StatusDescriptor {
  return (productType === "stl" ? lookup(STL_LINE_STATUS, status) : undefined) ?? lookup(LINE_STATUS, status) ?? UNKNOWN;
}

const ACTION_LABEL: Readonly<Record<string, string>> = {
  in_production: "Start production",
  ready_to_ship: "Mark ready to ship",
  shipped: "Mark shipped",
  delivered: "Mark delivered",
  returned: "Mark returned",
  ready_for_pickup: "Mark ready for pickup",
  picked_up: "Mark picked up",
  cancelled: "Cancel line",
};

export function describeTransitionAction(target: string, productType: string): string {
  if (productType === "stl" && target === "delivered") return "Mark STL emailed";
  return lookup(ACTION_LABEL, target) ?? "Update line";
}

const CANCEL_REASON: Readonly<Record<string, string>> = {
  refused: "Customer refused the order",
  no_show: "Customer didn't collect",
  other: "Other",
};

export function describeCancelReason(reason: string): string {
  return lookup(CANCEL_REASON, reason) ?? "Other";
}

// Admin refund status (backend RefundStatus) and kind (RefundKind).
const REFUND_STATUS: Readonly<Record<string, StatusDescriptor>> = {
  pending: { label: "Pending", tone: "warning" },
  settled: { label: "Settled", tone: "positive" },
  failed: { label: "Failed", tone: "negative" },
  voided: { label: "Voided", tone: "neutral" },
};

const REFUND_KIND: Readonly<Record<string, string>> = {
  admin: "Admin refund",
  cancellation: "Cancellation refund",
  late_capture: "Late capture refund",
};

export function describeAdminRefundStatus(status: string): StatusDescriptor {
  return lookup(REFUND_STATUS, status) ?? UNKNOWN;
}

// backend PaymentProvider: `cash` (recorded by an administrator) and
// `mock` (the only online provider until VS-032). Any other value is a
// future online provider.
export function describePaymentProvider(provider: string): string {
  if (provider === "cash") return "Cash";
  if (provider === "mock") return "Online (mock provider)";
  return "Online";
}

export function describeAdminRefundKind(kind: string): string {
  return lookup(REFUND_KIND, kind) ?? "Refund";
}

// ---------------------------------------------------------------------
// Order-level offers (no server flag; the POST re-checks and its 409 is shown)
// ---------------------------------------------------------------------

// Cash handover (ordering/domain/handover.py): a cash order with a
// fulfillment method, unpaid (payment_due), every live line at the ready
// state (delivery: shipped, pickup: ready_for_pickup) and none already
// handed over. The amount is typed by the administrator, never prefilled.
const READY: Readonly<Record<string, string>> = { delivery: "shipped", pickup: "ready_for_pickup" };

export function canRecordCashHandover(order: AdminOrderDetailDTO): boolean {
  if (order.payment_method !== "cash" || order.fulfillment_method === null || !order.payment_due) return false;
  const ready = lookup(READY, order.fulfillment_method);
  const live = order.lines.filter((line) => line.fulfillment_status !== "cancelled");
  return live.length > 0 && live.every((line) => line.fulfillment_status === ready);
}

// Order cancel (ordering/domain/cancellation.py admin_cancels): the
// physical lines still before shipping or collection, each one the server
// itself currently offers `cancelled` for. A `cancel_reason` is required
// when one of them takes one (ready_to_ship / ready_for_pickup), from the
// reasons the server lists for those lines.
const ADMIN_CANCELLABLE = new Set(["pending", "in_production", "ready_to_ship", "ready_for_pickup"]);

export interface OrderCancelOffer {
  lines: AdminOrderLineReadDTO[];
  reasons: CancelReason[];
  reasonRequired: boolean;
}

export function orderCancelOffer(order: AdminOrderDetailDTO): OrderCancelOffer | null {
  const lines = order.lines.filter(
    (line) =>
      line.product_type === "physical" &&
      ADMIN_CANCELLABLE.has(line.fulfillment_status) &&
      line.available_actions.some((action) => action.target_status === "cancelled")
  );
  if (lines.length === 0) return null;
  const perLine = lines.map(
    (line) => line.available_actions.find((action) => action.target_status === "cancelled")?.cancel_reasons ?? []
  );
  const reasons = Array.from(new Set(perLine.flat()));
  return { lines, reasons, reasonRequired: perLine.some((r) => r.length > 0) };
}

// ---------------------------------------------------------------------
// Errors (status + code + typed extensions only; never title/detail/msg)
// ---------------------------------------------------------------------

export type AdminOrderAction = "transition" | "cash-handover" | "cancel" | "note";

const REFUSAL: Readonly<Record<string, string>> = {
  payment_required: "This online order hasn't been paid, so it can't be fulfilled yet.",
  cash_handover_required: "Record the cash handover to mark this cash order delivered or picked up.",
  not_a_legal_edge: "That step isn't allowed from the line's current state.",
  line_closed: "This line is already closed (cancelled or refunded).",
  cancel_reason_required: "Choose a cancel reason for this step.",
  cancel_reason_not_allowed: "That cancel reason doesn't apply here.",
  refund_exceeds_available: "The refund for this cancellation would exceed what was paid, so nothing changed.",
  already_delivered: "This STL file is already marked as emailed.",
  not_awaiting_delivery: "This STL line isn't waiting to be emailed.",
  no_cancellable_line: "No line of this order can be cancelled now.",
  not_a_cash_order: "This isn't a cash order with a delivery or pickup, so there's no cash handover.",
  no_live_line: "Every line of this order is cancelled, so there's nothing to hand over.",
  already_recorded: "The cash handover for this order is already recorded.",
  lines_not_ready: "Every line must be shipped (delivery) or ready for pickup before recording the cash handover.",
};

export const ADMIN_ORDER_MESSAGES = {
  stateChanged: "This order changed, so that action couldn't be completed. The latest state is shown.",
  totalMismatch: "The order's totals don't match its lines or payment, so nothing changed. The team has been alerted.",
  notFound: "This order could not be found.",
  csrf: "Unable to verify your session. Please refresh the page and try again.",
  mfa: "Complete two-factor setup to manage orders.",
  session: "Your session has expired. Please sign in again.",
  rateLimited: "Too many requests. Please wait and try again.",
  validation: "Check the entered values and try again.",
  network: "We couldn't reach the server. Check the order before trying again.",
  generic: "Something went wrong. Please try again.",
} as const;

export interface AdminOrderErrorOutcome {
  message: string;
  // The order's own state explains the answer: re-read it.
  refetchOrder: boolean;
}

function isApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "kind" in value && "message" in value;
}

// CASH_AMOUNT_MISMATCH's typed `amount_due` extension ({amount_cents,
// currency}); anything else is treated as absent, never coerced.
function amountDueCents(error: ApiError): number | undefined {
  const raw = error.raw;
  if (typeof raw !== "object" || raw === null) return undefined;
  const due = (raw as Record<string, unknown>).amount_due;
  if (typeof due !== "object" || due === null) return undefined;
  const cents = (due as Record<string, unknown>).amount_cents;
  return typeof cents === "number" && Number.isInteger(cents) ? cents : undefined;
}

function money(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

export function describeAdminOrderError(error: unknown): AdminOrderErrorOutcome {
  const M = ADMIN_ORDER_MESSAGES;
  if (!isApiError(error)) return { message: M.generic, refetchOrder: false };
  if (error.kind === "csrf") return { message: M.csrf, refetchOrder: false };
  if (error.kind !== "http" || error.status === undefined) return { message: M.network, refetchOrder: true };
  switch (`${error.status} ${error.code ?? ""}`) {
    case "409 INVALID_STATE_TRANSITION": {
      const reason = readProblemString(error, "reason");
      return { message: (reason !== undefined ? lookup(REFUSAL, reason) : undefined) ?? M.stateChanged, refetchOrder: true };
    }
    case "409 ORDER_TOTAL_MISMATCH":
      return { message: M.totalMismatch, refetchOrder: true };
    case "422 CASH_AMOUNT_MISMATCH": {
      const cents = amountDueCents(error);
      return {
        message:
          cents !== undefined
            ? `The cash entered must be exactly the amount due (${money(cents)}).`
            : "The cash entered must be exactly the amount due.",
        refetchOrder: true,
      };
    }
    case "422 VALIDATION_ERROR":
      return { message: M.validation, refetchOrder: false };
    case "404 NOT_FOUND":
      return { message: M.notFound, refetchOrder: true };
    case "403 CSRF_INVALID":
      return { message: M.csrf, refetchOrder: false };
    case "401 MFA_REQUIRED":
      return { message: M.mfa, refetchOrder: false };
    case "401 AUTH_REQUIRED":
      return { message: M.session, refetchOrder: false };
    case "429 RATE_LIMITED":
      return { message: M.rateLimited, refetchOrder: false };
    default:
      return error.status >= 500 ? { message: M.network, refetchOrder: true } : { message: M.generic, refetchOrder: false };
  }
}
