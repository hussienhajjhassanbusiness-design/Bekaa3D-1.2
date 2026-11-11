import type { StatusBadgeTone } from "@/components/admin/StatusBadge";

// #ARCHITECTURE-BYI-PIPELINE (phase 6B-2) — backend 2dfb27b
// `custom_request_status` (engagement/domain/enums.py) and its ONLY edges
// (domain/custom_request.py PIPELINE, SRS 20.7):
//   new -> contacted
//   contacted -> quoted | lost
//   quoted -> in_progress | lost
//   in_progress -> completed
//   completed -> closed
//   closed, lost: terminal
// Moving to `quoted` requires quoted_amount_cents (1 to 100,000,000; the
// currency is set by the server, USD); no other move may carry an amount.
// The server derives `outcome`: `in_progress` is the win (work starts only
// after an off-platform agreement), `lost` the loss. A lead is never an
// order or a payment (BR-112). The server stays authoritative (409); this
// only decides which buttons to render.
export const CUSTOM_REQUEST_STATUSES = ["new", "contacted", "quoted", "in_progress", "completed", "closed", "lost"] as const;
export type CustomRequestStatus = (typeof CUSTOM_REQUEST_STATUSES)[number];
export type CustomRequestOutcome = "won" | "lost";

export const QUOTE_MIN_CENTS = 1;
export const QUOTE_MAX_CENTS = 100_000_000;

const PIPELINE: Record<CustomRequestStatus, readonly CustomRequestStatus[]> = {
  new: ["contacted"],
  contacted: ["quoted", "lost"],
  quoted: ["in_progress", "lost"],
  in_progress: ["completed"],
  completed: ["closed"],
  closed: [],
  lost: [],
};

export interface CustomRequestAction {
  target: CustomRequestStatus;
  label: string;
  confirm: string;
  needsQuote: boolean;
  destructive: boolean;
}

const ACTIONS: Record<Exclude<CustomRequestStatus, "new">, Omit<CustomRequestAction, "target">> = {
  contacted: { label: "Mark contacted", confirm: "You've been in touch with the requester.", needsQuote: false, destructive: false },
  quoted: { label: "Record quote", confirm: "Record the price you quoted. This doesn't charge anyone.", needsQuote: true, destructive: false },
  in_progress: { label: "Start work (won)", confirm: "The requester agreed off the platform. This counts the lead as won.", needsQuote: false, destructive: false },
  completed: { label: "Mark completed", confirm: "The work is finished.", needsQuote: false, destructive: false },
  closed: { label: "Close", confirm: "Close this request. It can't be reopened.", needsQuote: false, destructive: false },
  lost: { label: "Mark lost", confirm: "The requester didn't go ahead. It can't be reopened.", needsQuote: false, destructive: true },
};

export function isCustomRequestStatus(value: unknown): value is CustomRequestStatus {
  return typeof value === "string" && (CUSTOM_REQUEST_STATUSES as readonly string[]).includes(value);
}

export function getCustomRequestActions(status: CustomRequestStatus): CustomRequestAction[] {
  return PIPELINE[status].map((target) => ({ target, ...ACTIONS[target as Exclude<CustomRequestStatus, "new">] }));
}

const DESCRIPTIONS: Record<CustomRequestStatus, { label: string; tone: StatusBadgeTone }> = {
  new: { label: "New", tone: "warning" },
  contacted: { label: "Contacted", tone: "neutral" },
  quoted: { label: "Quoted", tone: "neutral" },
  in_progress: { label: "In progress", tone: "positive" },
  completed: { label: "Completed", tone: "positive" },
  closed: { label: "Closed", tone: "neutral" },
  lost: { label: "Lost", tone: "negative" },
};

export function describeCustomRequestStatus(status: string): { label: string; tone: StatusBadgeTone } {
  return isCustomRequestStatus(status) ? DESCRIPTIONS[status] : { label: status, tone: "neutral" };
}

export function describeOutcome(outcome: CustomRequestOutcome | null): string {
  if (outcome === "won") return "Won";
  if (outcome === "lost") return "Lost";
  return "Open";
}
