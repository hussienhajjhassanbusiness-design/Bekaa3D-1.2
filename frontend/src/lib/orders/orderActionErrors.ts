import type { ApiError } from "@/lib/api/ApiError";
import { readProblemString } from "@/lib/api/problemExtensions";

// #FVS031-ORDER-ACTION-ERRORS (phase 5G)
//
// Classifies every failure of the three customer order actions on status +
// Problem.code + the typed `reason` extension only (backend 2dfb27b
// ordering/api/cancel.py `_RESPONSES`, ordering/api/receipt.py). Problem
// title/detail and validation `msg` are never returned; all copy is ours.
//
//   refetchOrder - the order's own state explains the answer (a refusal,
//                  a 404, or an unknown outcome): re-read the canonical
//                  order detail so the page shows the server's truth.
export type OrderAction = "cancel" | "confirm-receipt" | "report-problem";

export type OrderActionErrorKind =
  "refused" | "not-found" | "session-expired" | "verify-email" | "uncertain" | "message";

export interface OrderActionErrorOutcome {
  kind: OrderActionErrorKind;
  message: string;
  refetchOrder: boolean;
}

export const ORDER_ACTION_MESSAGES = {
  notCancellable:
    "This order can no longer be cancelled, so nothing was changed. Its current status is shown below.",
  noDeliveredLine: "None of the items in this order has been delivered or picked up yet.",
  stateChanged: "This order has changed, so that action isn't available right now. Its current status is shown below.",
  notFound: "We couldn't find this order in your account.",
  csrf: "Unable to verify your session. Please refresh the page and try again.",
  sessionExpired: "Your session has expired. Please sign in again to continue.",
  verifyEmail: "Verify your email address before making changes to this order.",
  invalidMessage: "We couldn't send that message. Check it and try again.",
  rateLimited: "Too many requests. Please wait a while and try again.",
  uncertain: "We couldn't confirm whether that went through. Check the order below before trying again.",
  generic: {
    cancel: "We couldn't cancel this order. Please try again.",
    "confirm-receipt": "We couldn't record that you received your items. Please try again.",
    "report-problem": "We couldn't send your report. Please try again.",
  },
} as const;

const M = ORDER_ACTION_MESSAGES;

const REFUSAL_REASONS: Readonly<Record<string, string>> = {
  no_delivered_line: M.noDeliveredLine,
};

function isApiError(value: unknown): value is ApiError {
  return typeof value === "object" && value !== null && "kind" in value && "message" in value;
}

function own(table: Readonly<Record<string, string>>, key: string | undefined): string | undefined {
  return key !== undefined && Object.prototype.hasOwnProperty.call(table, key) ? table[key] : undefined;
}

function formatWait(seconds: number): string {
  if (seconds >= 3600) {
    const hours = Math.round(seconds / 3600);
    return `${hours} hour${hours === 1 ? "" : "s"}`;
  }
  if (seconds >= 60) {
    const minutes = Math.round(seconds / 60);
    return `${minutes} minute${minutes === 1 ? "" : "s"}`;
  }
  return `${seconds} second${seconds === 1 ? "" : "s"}`;
}

function outcome(kind: OrderActionErrorKind, message: string, refetchOrder = false): OrderActionErrorOutcome {
  return { kind, message, refetchOrder };
}

export function describeOrderActionError(action: OrderAction, error: unknown): OrderActionErrorOutcome {
  if (!isApiError(error)) {
    return outcome("message", M.generic[action]);
  }
  if (error.kind === "csrf") {
    // A local precondition: no request was sent.
    return outcome("message", M.csrf);
  }
  if (error.kind !== "http" || error.status === undefined) {
    return outcome("uncertain", M.uncertain, true);
  }

  switch (`${error.status} ${error.code ?? ""}`) {
    case "409 ORDER_NOT_CANCELLABLE":
      return outcome("refused", M.notCancellable, true);
    case "409 INVALID_STATE_TRANSITION":
      return outcome("refused", own(REFUSAL_REASONS, readProblemString(error, "reason")) ?? M.stateChanged, true);
    case "404 NOT_FOUND":
      return outcome("not-found", M.notFound, true);
    case "403 CSRF_INVALID":
      return outcome("message", M.csrf);
    case "403 EMAIL_VERIFICATION_REQUIRED":
      return outcome("verify-email", M.verifyEmail);
    case "401 AUTH_REQUIRED":
      return outcome("session-expired", M.sessionExpired);
    case "429 RATE_LIMITED":
      return outcome(
        "message",
        error.retryAfterSeconds !== undefined
          ? `Too many requests. Please try again in ${formatWait(error.retryAfterSeconds)}.`
          : M.rateLimited
      );
    default:
      if (error.status === 422 && action === "report-problem") {
        return outcome("message", M.invalidMessage);
      }
      return error.status >= 500 ? outcome("uncertain", M.uncertain, true) : outcome("message", M.generic[action]);
  }
}
