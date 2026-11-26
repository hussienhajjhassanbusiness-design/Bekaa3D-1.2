import { apiClient } from "@/lib/api/apiClient";
import { authenticatedRequest } from "@/lib/auth/authenticatedRequest";
import type { NotificationPageDTO, NotificationReadDTO, NotificationsQueryParams } from "./notificationTypes";

// #ARCHITECTURE-NOTIFICATIONS-QUERY-ADAPTER
//
// Confirmed wire contract (docs/backend-handoff/openapi.json,
// paths./api/v1/me/notifications.get) — every key below is a direct quote
// of a real query parameter name. A parameter is included only when
// actually set, same omit-when-unset rule productsApi.ts already follows.
export function buildNotificationsSearchParams(params: NotificationsQueryParams): URLSearchParams {
  const search = new URLSearchParams();

  if (params.cursor) search.set("cursor", params.cursor);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.read !== undefined) search.set("read", String(params.read));

  return search;
}

// Both calls are authenticated (session cookie); authenticatedRequest
// gives both the one confirmed refresh-then-retry-once behavior on a 401
// AUTH_REQUIRED, matching every other authenticated call in this codebase
// — never a bespoke retry loop here.
async function listNotifications(params: NotificationsQueryParams): Promise<NotificationPageDTO> {
  const search = buildNotificationsSearchParams(params).toString();
  const path = search ? `/api/v1/me/notifications?${search}` : "/api/v1/me/notifications";
  return authenticatedRequest(() => apiClient.get<NotificationPageDTO>(path));
}

async function setNotificationRead(notificationId: string, read: boolean): Promise<NotificationReadDTO> {
  return authenticatedRequest(() =>
    apiClient.patch<NotificationReadDTO>(
      `/api/v1/me/notifications/${encodeURIComponent(notificationId)}`,
      { read },
      { csrf: true }
    )
  );
}

export const notificationsApi = { listNotifications, setNotificationRead };

export const notificationsKeys = {
  root: ["notifications"] as const,
  list: (params: NotificationsQueryParams) => [...notificationsKeys.root, "list", params] as const,
};
