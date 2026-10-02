"use client";

import { Button } from "@/components/forms/Button";
import { NOTIFICATION_RENDERERS, type NotificationItemModel } from "./notificationTypes";

export interface NotificationItemProps {
  notification: NotificationItemModel;
  onToggleRead: (id: string, nextIsRead: boolean) => void;
  isPending?: boolean;
}

// #FVS008-NOTIFICATION-CENTER
//
// Generic presentation only — no network call, no TanStack Query
// ownership, no persistence. `type` is looked up in the shared
// NOTIFICATION_RENDERERS registry (notificationTypes.ts); any type with
// no entry (every type exists in that state today — the registry starts
// empty) falls back to the notification's own plain title/body, never a
// crash. Title/body are always rendered as plain text (JSX
// interpolation), never dangerouslySetInnerHTML.
export function NotificationItem({ notification, onToggleRead, isPending = false }: NotificationItemProps) {
  const renderer = NOTIFICATION_RENDERERS[notification.type];
  const { title, body } = renderer ? renderer(notification) : notification;

  return (
    <div className="flex items-start justify-between gap-3 py-3">
      <div>
        <p className="text-body font-semibold text-text-primary">{title}</p>
        <p className="mt-1 text-body text-text-secondary">{body}</p>
        <p className="mt-1 text-caption text-text-secondary">{notification.isRead ? "Read" : "Unread"}</p>
      </div>
      <Button
        type="button"
        onClick={() => onToggleRead(notification.id, !notification.isRead)}
        disabled={isPending}
        isLoading={isPending}
      >
        {notification.isRead ? "Mark unread" : "Mark read"}
      </Button>
    </div>
  );
}
