import type { StatusBadgeTone } from "@/components/admin/StatusBadge";

// #ARCHITECTURE-CONTACT-STATUS-WORKFLOW
//
// Frontend-normalized status model — NOT a claim about the backend's
// real serialized enum strings, which are still NEEDS BACKEND
// CONFIRMATION (FVS-017-IMPLEMENTATION-PLAN.md §1). A future API
// adapter maps whatever VS-015's admin half actually returns onto this
// union. The linear sequence below (new → read → replied → archived,
// no skips, no reverse transitions) is confirmed PRODUCT behavior —
// FRONTEND-VERTICAL-SLICE-PLAN.md's own FVS-017 capability line states
// exactly this sequence — not an invented workflow engine.
export type ContactMessageStatus = "new" | "read" | "replied" | "archived";

export interface ContactMessageAction {
  nextStatus: ContactMessageStatus;
  label: string;
}

const TRANSITIONS: Record<ContactMessageStatus, ContactMessageAction | null> = {
  new: { nextStatus: "read", label: "Mark read" },
  read: { nextStatus: "replied", label: "Mark replied" },
  replied: { nextStatus: "archived", label: "Archive" },
  archived: null,
};

// The ONLY legal next action for a status, or null at the terminal
// state — a caller can never reach an illegal transition (e.g.
// "archived" -> "read") through this API, since no other path exists.
export function getNextContactMessageAction(status: ContactMessageStatus): ContactMessageAction | null {
  return TRANSITIONS[status];
}

const STATUS_DESCRIPTIONS: Record<ContactMessageStatus, { label: string; tone: StatusBadgeTone }> = {
  new: { label: "New", tone: "warning" },
  read: { label: "Read", tone: "neutral" },
  replied: { label: "Replied", tone: "positive" },
  archived: { label: "Archived", tone: "neutral" },
};

export function describeContactMessageStatus(status: ContactMessageStatus): { label: string; tone: StatusBadgeTone } {
  return STATUS_DESCRIPTIONS[status];
}
