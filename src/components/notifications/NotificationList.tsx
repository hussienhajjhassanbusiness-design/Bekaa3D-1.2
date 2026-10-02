"use client";

import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { NotificationItem } from "./NotificationItem";
import type { NotificationItemModel } from "./notificationTypes";

export interface NotificationListProps {
  notifications: readonly NotificationItemModel[];
  onToggleRead: (id: string, nextIsRead: boolean) => void;
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
  pendingId?: string | null;
  canLoadMore?: boolean;
  isLoadingMore?: boolean;
  onLoadMore?: () => void;
}

const EMPTY_MESSAGE = "You have no notifications yet.";
const DEFAULT_ERROR_MESSAGE = "We couldn't load your notifications. Please try again.";

// #FVS008-NOTIFICATION-CENTER
//
// Presentational list states only — loading/error/empty/populated, plus
// a fully generic load-more seam (canLoadMore/isLoadingMore/onLoadMore —
// no page/cursor field assumed, since the real pagination shape is still
// NEEDS BACKEND CONFIRMATION). errorMessage is already a safe, external
// string; this component never parses a raw backend error.
export function NotificationList({
  notifications,
  onToggleRead,
  isLoading = false,
  isError = false,
  errorMessage,
  onRetry,
  pendingId = null,
  canLoadMore = false,
  isLoadingMore = false,
  onLoadMore,
}: NotificationListProps) {
  if (isLoading) {
    return (
      <div role="status">
        <span className="sr-only">Loading notifications…</span>
        {[0, 1, 2].map((index) => (
          <div
            key={index}
            aria-hidden="true"
            className="mt-2 h-12 animate-pulse rounded bg-neutral-200 motion-reduce:animate-none"
          />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        <Alert variant="error" message={errorMessage ?? DEFAULT_ERROR_MESSAGE} />
        {onRetry && (
          <Button onClick={onRetry} className="mt-2">
            Retry
          </Button>
        )}
      </div>
    );
  }

  if (notifications.length === 0) {
    return <p className="text-body text-text-secondary">{EMPTY_MESSAGE}</p>;
  }

  return (
    <div>
      <ul>
        {notifications.map((notification) => (
          <li key={notification.id}>
            <NotificationItem
              notification={notification}
              onToggleRead={onToggleRead}
              isPending={pendingId === notification.id}
            />
          </li>
        ))}
      </ul>
      {canLoadMore && (
        <Button onClick={onLoadMore} disabled={isLoadingMore} isLoading={isLoadingMore} className="mt-2">
          Load more
        </Button>
      )}
    </div>
  );
}
