import type { NotificationItemModel } from "@/components/notifications/notificationTypes";
import type { NotificationReadDTO } from "./notificationTypes";

// Phase 2 auth/account batch — the real API adapter notificationTypes.ts
// (src/components/notifications/) already anticipated: "once the real
// contract lands, a future API adapter maps it onto NotificationItemModel
// in one place." The real NotificationRead has no title/body field at
// all — only id/type/payload/read/created_at — so both are DERIVED here,
// never read off the wire. `payload.event` (BACKEND-RESPONSE.md P2-5: the
// event registry is currently empty) is read only as an optional, safe
// string — any other shape (number/object/array/absent) falls back to the
// plain per-type label, never a crash, and the backend-authored string is
// shown only as plain text (JSX text interpolation in NotificationItem),
// never dangerouslySetInnerHTML.
// Keyed by the current NotificationType enum (openapi.json, backend 2dfb27b).
// Deliberately a string-keyed lookup, not an exhaustive switch: an unknown
// future type falls back to UNKNOWN_TYPE_LABEL.
const TYPE_LABELS: Readonly<Record<string, string>> = {
  account: "Account",
  order: "Order",
  payment: "Payment",
  refund: "Refund",
  offer: "Offer",
  download: "Download",
  custom_request: "Custom request",
};
const UNKNOWN_TYPE_LABEL = "Notification";

function labelForType(type: string): string {
  return TYPE_LABELS[type] ?? UNKNOWN_TYPE_LABEL;
}

function safeEventString(payload: Record<string, unknown>): string | null {
  const event = payload["event"];
  return typeof event === "string" && event.length > 0 ? event : null;
}

export function adaptNotification(dto: NotificationReadDTO): NotificationItemModel {
  const label = labelForType(dto.type);
  const event = safeEventString(dto.payload);

  return {
    id: dto.id,
    type: dto.type,
    title: label,
    body: event ? `${label} update: ${event}` : `You have a new ${label.toLowerCase()} notification.`,
    isRead: dto.read,
    createdAt: dto.created_at,
  };
}
