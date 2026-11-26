// FVS-008-IMPLEMENTATION-PLAN.md T01 (CAN IMPLEMENT NOW — contract-
// independent).
//
// #ARCHITECTURE-NOTIFICATION-ADAPTER
//
// Frontend-NORMALIZED UI model, not a claim about the backend response.
// The real GET /api/v1/me/notifications envelope, field names, and
// pagination shape are all NEEDS BACKEND CONFIRMATION
// (FVS-008-IMPLEMENTATION-PLAN.md §1). The backend response is
// intentionally isolated from NotificationItem/NotificationList by this
// type: once the real contract lands, a future API adapter maps it onto
// NotificationItemModel in one place. Future backend-contract changes
// belong in that adapter, not in every component that renders a
// notification.
//
// No link field exists here — nothing in the UI needs one yet; add only
// when a real consumer does. `createdAt` (Batch 5) is the real
// NotificationRead.created_at, shown as the row timestamp; optional so a
// model built without it simply renders no time.
export interface NotificationItemModel {
  id: string;
  type: string;
  title: string;
  body: string;
  isRead: boolean;
  createdAt?: string;
}

// #SHARED-NOTIFICATION-RENDERERS
//
// The seam future slices use to add their own event-specific rendering
// (order paid, offer countered, etc.) WITHOUT touching NotificationItem
// itself. Deliberately empty at FVS-008 — not even a commerce-type
// example — since VS-008 itself defines only the generic transport; a
// `type` this registry has no entry for always falls back to the plain
// title/body render in NotificationItem, never a crash.
export type NotificationRenderer = (notification: NotificationItemModel) => {
  title: string;
  body: string;
};

export const NOTIFICATION_RENDERERS: Readonly<Record<string, NotificationRenderer>> = {};
