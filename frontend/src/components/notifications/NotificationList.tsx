"use client";

import { Button } from "@/components/forms/Button";
import { Alert } from "@/components/feedback/Alert";
import { EmptyState } from "@/components/feedback/EmptyState";
import { LoadMore } from "@/components/feedback/LoadMore";
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
const LIST_CARD_CLASSES =
  "overflow-hidden rounded-card border border-outline-variant/30 bg-surface-container-lowest shadow-sm";

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
      <div role="status" className={`${LIST_CARD_CLASSES} divide-y divide-outline-variant/30`}>
        <span className="sr-only">Loading notifications…</span>
        {[0, 1, 2].map((index) => (
          <div key={index} aria-hidden="true" className="flex gap-4 p-4 tablet:p-6">
            <div className="hidden h-10 w-10 shrink-0 animate-pulse rounded-lg bg-surface-container-high motion-reduce:animate-none tablet:block" />
            <div className="flex flex-1 flex-col gap-2">
              <div className="h-4 w-1/3 animate-pulse rounded bg-surface-container-high motion-reduce:animate-none" />
              <div className="h-4 w-2/3 animate-pulse rounded bg-surface-container-high motion-reduce:animate-none" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className={`${LIST_CARD_CLASSES} p-6`}>
        <Alert variant="error" message={errorMessage ?? DEFAULT_ERROR_MESSAGE} />
        {onRetry && (
          <Button onClick={onRetry} className="mt-4">
            Retry
          </Button>
        )}
      </div>
    );
  }

  if (notifications.length === 0) {
    return (
      <div className={LIST_CARD_CLASSES}>
        <EmptyState icon="notifications" message={EMPTY_MESSAGE} />
      </div>
    );
  }

  return (
    <div>
      <ul className={`${LIST_CARD_CLASSES} divide-y divide-outline-variant/30`}>
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
      <LoadMore hasMore={canLoadMore} onLoadMore={() => onLoadMore?.()} isLoading={isLoadingMore} />
    </div>
  );
}
