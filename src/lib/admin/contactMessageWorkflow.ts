import type { StatusBadgeTone } from "@/components/admin/StatusBadge";

// #ARCHITECTURE-CONTACT-STATUS-WORKFLOW (phase 6B-1)
//
// Backend 2dfb27b `contact_message_status` (engagement/domain/enums.py),
// declaration order = queue order: new -> read -> replied -> archived.
// Transitions are FORWARD ONLY, SKIPS ALLOWED (contact_message.py
// can_transition, VS-033 Q6): any later status is a legal target; a
// backwards move is 409 INVALID_STATE_TRANSITION. Staying put is a no-op,
// so it is never offered as an action. The server stays authoritative —
// this only decides which buttons to render.
export const CONTACT_MESSAGE_STATUSES = ["new", "read", "replied", "archived"] as const;
export type ContactMessageStatus = (typeof CONTACT_MESSAGE_STATUSES)[number];

export interface ContactMessageAction {
  nextStatus: ContactMessageStatus;
  label: string;
}

const ACTION_LABELS: Record<ContactMessageStatus, string> = {
  new: "Mark new",
  read: "Mark read",
  replied: "Mark replied",
  archived: "Archive",
};

export function isContactMessageStatus(value: unknown): value is ContactMessageStatus {
  return typeof value === "string" && (CONTACT_MESSAGE_STATUSES as readonly string[]).includes(value);
}

// Every forward target from `status`, nearest first; empty at `archived`.
export function getContactMessageActions(status: ContactMessageStatus): ContactMessageAction[] {
  const index = CONTACT_MESSAGE_STATUSES.indexOf(status);
  return CONTACT_MESSAGE_STATUSES.slice(index + 1).map((next) => ({ nextStatus: next, label: ACTION_LABELS[next] }));
}

const STATUS_DESCRIPTIONS: Record<ContactMessageStatus, { label: string; tone: StatusBadgeTone }> = {
  new: { label: "New", tone: "warning" },
  read: { label: "Read", tone: "neutral" },
  replied: { label: "Replied", tone: "positive" },
  archived: { label: "Archived", tone: "neutral" },
};

// An unknown value (a future enum member) renders as itself, never crashes.
export function describeContactMessageStatus(status: string): { label: string; tone: StatusBadgeTone } {
  return isContactMessageStatus(status) ? STATUS_DESCRIPTIONS[status] : { label: status, tone: "neutral" };
}
