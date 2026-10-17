// Phase 2 auth/account batch — confirmed wire contract (docs/backend-
// handoff/openapi.json: components.schemas.NotificationRead/NotificationPage/
// NotificationUpdate). `type` is the six-value NotificationType enum
// (account/order/payment/refund/offer/download); the specific event lives
// in the free-form `payload` object under `payload.event`, which may be
// absent or any shape — the backend's own design intentionally keeps this
// extensible without a schema migration per new business event.
export type NotificationType = "account" | "order" | "payment" | "refund" | "offer" | "download";

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
