// Phase 2 auth/account batch — confirmed wire contract (docs/backend-
// handoff/openapi.json: components.schemas.NotificationRead/NotificationPage/
// NotificationUpdate). `type` is the NotificationType enum
// (see below); the specific event lives
// in the free-form `payload` object under `payload.event`, which may be
// absent or any shape — the backend's own design intentionally keeps this
// extensible without a schema migration per new business event.
// Current backend contract (openapi.json NotificationType, backend 2dfb27b)
// adds `custom_request` (ADR-030). `download` remains a legacy category label
// only (ADR-019 removed downloads) — never build download UI from it.
// NotificationReadDTO.type stays `string` on purpose: an unknown future type
// must reach the adapter and fall back to the generic label, never crash.
export type NotificationType =
  | "account"
  | "order"
  | "payment"
  | "refund"
  | "offer"
  | "download"
  | "custom_request";

export interface NotificationReadDTO {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  read: boolean;
  created_at: string;
}

export interface NotificationPageDTO {
  items: NotificationReadDTO[];
  next_cursor: string | null;
}

export interface NotificationsQueryParams {
  cursor?: string;
  limit?: number;
  read?: boolean;
}
