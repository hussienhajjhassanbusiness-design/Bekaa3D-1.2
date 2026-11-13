"use client";

import { useId } from "react";
import { Button } from "@/components/forms/Button";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { Icon, type IconName } from "@/components/ui/Icon";
import { NOTIFICATION_RENDERERS, type NotificationItemModel } from "./notificationTypes";

export interface NotificationItemProps {
  notification: NotificationItemModel;
  onToggleRead: (id: string, nextIsRead: boolean) => void;
  isPending?: boolean;
}

// Decorative glyph per real NotificationType (presentation only — the
// visible title already names the type). Unknown types get the bell.
const TYPE_ICONS: Readonly<Record<string, IconName>> = {
  account: "person",
  order: "shopping-bag",
  offer: "sell",
  download: "download",
  custom_request: "lightbulb",
};

// The server's ISO instant in the viewer's time zone; an unparsable value
// renders no time rather than "Invalid Date".
function formatTimestamp(iso: string | undefined): string | null {
  if (!iso) {
    return null;
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" }).format(date);
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
//
// Batch 5 (Stitch §46 rows, DERIVED page): type glyph tile, title as the
// row heading, "Unread"/"Read" as a visible text badge (never colour
// alone; unread rows also get a tinted background and a primary rail),
// and the real created_at as a <time>.
export function NotificationItem({ notification, onToggleRead, isPending = false }: NotificationItemProps) {
  const renderer = NOTIFICATION_RENDERERS[notification.type];
  const { title, body } = renderer ? renderer(notification) : notification;
  const headingId = useId();
  const timestamp = formatTimestamp(notification.createdAt);
  const isUnread = !notification.isRead;

  return (
    <article
      aria-labelledby={headingId}
      className={`flex flex-col gap-4 border-l-4 p-4 tablet:flex-row tablet:items-start tablet:p-6 ${
        isUnread ? "border-l-primary bg-surface-container-low/70" : "border-l-transparent"
      }`}
    >
      <div
        aria-hidden="true"
        className={`hidden h-10 w-10 shrink-0 items-center justify-center rounded-lg tablet:flex ${
          isUnread ? "bg-primary/10 text-primary" : "bg-surface-container text-on-surface-variant"
        }`}
      >
        <Icon name={TYPE_ICONS[notification.type] ?? "notifications"} className="h-5 w-5" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2
            id={headingId}
            className={`min-w-0 break-words text-title-sm text-on-surface ${isUnread ? "font-bold" : "font-semibold"}`}
          >
            {title}
          </h2>
          <StatusBadge label={notification.isRead ? "Read" : "Unread"} tone={notification.isRead ? "neutral" : "positive"} />
        </div>
        <p className="mt-1 break-words text-body-md text-on-surface-variant">{body}</p>
        {timestamp && (
          <p className="mt-2 flex items-center gap-1.5 font-label text-label-sm text-on-surface-variant">
            <Icon name="schedule" className="h-4 w-4" />
            <time dateTime={notification.createdAt}>{timestamp}</time>
          </p>
        )}
      </div>

      <Button
        type="button"
        variant="outline"
        onClick={() => onToggleRead(notification.id, !notification.isRead)}
        disabled={isPending}
        isLoading={isPending}
        className="self-start"
      >
        {notification.isRead ? "Mark unread" : "Mark read"}
      </Button>
    </article>
  );
}
